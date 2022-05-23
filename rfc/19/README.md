---
domain: github.com
shortname: 19/EVERULES
name: Events and Rules
status: raw
editor: Mandar Sawant <mandar.sawant@seagate.com>
---

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

## Abstract

Define events that Hare needs to handle that are received in Hare's event queue (EQ) and from Motr.
Define payload formats corresponding to events that is required to submit an event to EQ or BQ.

## Event payload format

Event payload MUST be in following JSON format:

```json
{
  "obj_type": "rack/enclosure/controller/node/drive/process",
  "obj_name": "object name provided to Motr configuration, e.g. wwn id",
  "obj_state": "Failed/online"
}
```

### Suported object types and values

(Case sensitive.)

| Type | ID | [state](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L119) |
| --- | --- | --- |
| rack | rack identifier | Online, Failed |
| enclosure | enclosure identifier | Online, Failed |
| controller | controller identifier | Online, Failed |
| node | node hostname, e.g. ssc-vm-c-0553.colo.seagate.com | Online, Failed |
| drive | drive name, e.g. sdb, vdb, wwn | Online, Failed |
| process | process identifier | Online, Failed |


## Rules and effects

| Rule | Effect |
| --- | --- |
| device-state-set | Set the given device (rack/enclosure/controller/drive) state in consul and Motr. |
| sns-repair | Set the device and pool state to `M0_NC_REPAIR` in Consul and Motr ioservices and start SNS repair. |
| sns-rebalance | Set the device and pool state to `M0_NC_REBALANCE` in Consul and Motr io services and start SNS rebalance. |
| sns-repair-pause | Pause ongoing SNS repair operation, ioservices MUST return status as [CM_STATUS_PAUSED](https://github.com/Seagate/cortx-motr/blob/dev/cm/repreb/cm.h#L54)|
| sns-rebalance-pause | Pause ongoing SNS rebalance operation, ioservices MUST return status as CM_STATUS_PAUSED. |
| sns-repair-abort | Abort ongoing SNS repair operation, ioservices MUST return CM_STATUS_IDLE on successful abort. |
| sns-rebalance-abort | Abort ongoing SNS rebalance operation, ioservices MUST return CM_STATUS_IDLE on successful abort. |

## Motr event types and handling

### M0_HA_MSG_STOB_IOQ

[\[stob/ioq_error.h:38\]](https://github.com/Seagate/cortx-motr/blob/dev/stob/ioq_error.h#L38)

This event is received as a [`m0_ha_msg`](https://github.com/Seagate/cortx-motr/blob/dev/ha/msg.h#L113) which mainly comprises of motr fid for `m0_conf_sdev` Motr configuration object.

Motr pool machine uses `m0_conf_drive` configuration object which is mapped one to one with `m0_conf_sdev`.

Hax event handler corresponding to this event MUST map the sdev fid to drive fid to create a [`ha_note`](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L158) to notify Motr about the failure. On receiving this event, Hax MUST Log an ERROR message to systemd logs and MUST not device failure event to Motr processes immediately.

#### M0_HA_MSG_EVENT_PROCESS

[\[conf/ha.h:47\]](https://github.com/Seagate/cortx-motr/blob/dev/conf/ha.h#L47)

- Update process status in Consul KV. On receiving a [`M0_CONF_HA_PROCESS_STOPPED`](https://github.com/Seagate/cortx-motr/blob/dev/conf/ha.h#L70) event, hax MUST broadcast `M0_NC_FAILED` for that process to all the Motr services.

#### M0_HA_MSG_SNS_ERR

Post an event to BQ to handle sns error. The handler MUST broadcast `CM_OP_REPAIR_ABORT` or `CM_OP_REBALANCE_ABORT` for the ongoing SNS operation (repair/rebalance) using spiel interface to all the Motr processes.

## Other events

### Device event reported via h0q

- External applications will report a device failure or online event using h0q utility comprising of universal device name or identifier and the state. Hare MUST convert the universal device name or identifier to Motr specific identifier (FID) and post a `M0_NC_FAILED` event to BQ for the corresponding device's Motr FID.
- Hare Consul KV MUST have appropriate mappings for universal device names to Motr identifiers for all the supported devices used in Motr configuration. If Hare is not able to map a device name to its corresponding Motr identifier then an appropriate error MUST be logged.

#### Consul service failure / Motr process failure

- Consul service failure is mapped to process failure. Thus Hare MUST post a `M0_NC_FAILED` event for all the services belonging to the failed process to BQ.

## [HA states of Motr objects](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L118)

### M0_NC_FAILED

- Received by Hare from Motr or is a broadcast from Hare to Motr using BQ in case of a Motr device or service failures.
- Hare MUST post a BQ event - `M0_NC_FAILED` - to all Motr processes for a device that is reported as failed and update the device state in Consul KV.

#### M0_NC_TRANSIENT

- Post a BQ event for Motr devices in case the parent device or service fails in the Motr configuration hierarchy.

#### M0_NC_REPAIR

- Post a BQ event to Motr ioservices for failed Motr device(s) to be repaired.
- This is also received from Motr process in case of incomplete Motr SNS repair, typically due to failure.
  Motr sends `M0_HA_MSG_SNS_ERR` in case of SNS operation failure.
  Hare maintains the [device state](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L118). Depending upon the SNS operation identified by the corresponding device state, Hare MUST broadcast the respective SNS abort, `CM_OP_REPAIR_ABORT` in this case, to all the Motr ioservices.

#### M0_NC_REPAIRED

Received from Motr after successfull completion of SNS repair for Motr device. Hare MUST post a BQ event, `M0_NC_REPAIRED`, to all the Motr processes on receiving `M0_NC_REPAIRED` from all the Motr ioservices and update the device state in Consul KV.

#### M0_NC_REBALANCE

- Post a BQ event from Hare to all the Motr processes before starting SNS rebalance operation when Hare receives a device replacement event corresponding to repaired device(s).
- This is also received from Motr process in case of incomplete Motr SNS rebalance, typically due to failure.
  Motr sends `M0_HA_MSG_SNS_ERR` in case of SNS operation failure.
  Hare maintains the [device state](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L118).
  Depending upon the SNS operation identified by the corresponding device state, Hare MUST post a BQ event, `CM_OP_REBALANCE_ABORT` in this case, to all the Motr ioservices.
  Hare MUST accordingly update the device state as well in Consul KV.

#### M0_NC_ONLINE

- Received by Hare from every Motr process on successfull completion of SNS rebalance operation on a device.
- Hare MUST post a BQ event, `M0_NC_ONLINE`, to all Motr processes on receiving completion of SNS rebalance from all the Motr processes and update the same for the device state in Consul KV.

#### SNS operation status

[\[cm/repreb/cm.h\]](https://github.com/Seagate/cortx-motr/blob/dev/cm/repreb/cm.h)

- Hare MUST handle `CM_OP_REPAIR_STATUS`/`CM_OP_REBALANCE_STATUS` and post a BQ event that will use spiel interface to fetch per Motr process sns operation status.
- Hare MUST handle per device status event using hctl interface.

#### SNS operation ABORT/PAUSE/RESUME

- Post a BQ event to abort, pause or resume SNS operation.
  The event handler MUST use spiel interface to send `CM_OP_REPAIR_ABORT`/`CM_OP_REBALANCE_ABORT`, `CM_OP_REPAIR_PAUSE`/`CM_OP_REBALANCE_PAUSE` or `CM_OP_REPAIR_RESUME`/`CM_OP_REBALANCE_RESUME` to abort, pause or resume SNS operation.
- Hare MUST identify the ongoing SNS operation type, Repair or Rebalance, using the device status from Consul KV and accordingly MUST broadcast `CM_OP_REPAIR_ABORT` or `CM_OP_REBALANCE_ABORT` respectively.
