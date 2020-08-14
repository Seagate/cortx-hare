---
domain: github.com
shortname: 17/EVT
name: Event types
status: raw
editor: Mandar Sawant <mandar.sawant@seagate.com>
---

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

## Abstract

Hare handles various events delivered to it by Motr, HA or explicitly using some cli via Hare [event queue](https://github.com/Seagate/cortx-hare/blob/dev/rfc/16/README.md#event-queue-eq) mechanism.
Hare will receive and MUST send HA events to Motr in Motr [ha msg](https://github.com/Seagate/cortx-motr/blob/dev/ha/msg.h) format.
Every object in Motr corresponding to a device or service is represented by a unique identifier.
Hare MUST use this Motr identifier to find corresponding active actions against a Motr object and to notify changes in its states.

## Motr event types and handling

#### M0_HA_MSG_STOB_IOQ
- Create and post a device failure event, M0_NC_FAILED, to the event queue.
- This MUST trigger disk failure rule handler.
  - Rule MUST broadcast the failure event to motr services.
  - Create and post an event in event queue to trigger SNS repair rule if required.

#### M0_HA_MSG_EVENT_PROCESS
- Update process status in Consul KV.

#### M0_HA_MSG_BE_IO_ERR
- Create and post a failure event for be device to broadcast queue to broadcast the failure to motr device.
- Create and post an event to event queue

#### M0_HA_MSG_SNS_ERR
- Create and post an event to queue.
- This should trigger a SNS rule to check and abort an ongoing SNS operation (repair/rebalance).

## Other events and handling

#### Disk Failure reported via external interface 
- Disk failure event is posted to event queue. This MUST trigger disk failure handler rule.

#### Consul service failure (Motr process failure)
- Post an event to event queue. This MUST invoke service/node failure handler.
- Service/node failure handler rule MUST post M0_NC_FAILED event for Motr services in the hierarchy of the failed Motr process.

## [HA states of Motr objects](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L118)

#### M0_NC_FAILED
- Received by Hare from Motr or is a broadcast from Hare to Motr in case of a Motr device or service failures.
- Hare MUST broadcast M0_NC_FAILED to all Motr processes for a device that is reported as failed.
 
#### M0_NC_TRANSIENT
- Broadcast from Hare for Motr devices in case the parent device or service fails in the hierarchy. 

#### M0_NC_REPAIR
- Broadcast by Hare to Motr processes for Motr device(s) to be repaired.
- This is also received from Motr process in case of incomplete Motr SNS repair, typically due to failure.
  Motr also sends M0_HA_MSG_SNS_ERR in case of SNS operation failure. Hare MUST take appropriate action to send SNS operation abort and set device states back to M0_NC_FAILED.

#### M0_NC_REPAIRED
Received from Motr after successfull completion of SNS repair for Motr device. Hare MUST broadcast M0_NC_REPAIRED to all the Motr processes on receiving M0_NC_REPAIRED from everyone.

#### M0_NC_REBALANCE
- A broadcast from Hare to all the Motr processes when Hare receives a device replacement event corresponding to a failed device.
- A disk replacement event MUST trigger a corresponding Hare rule to start SNS rebalance on the device.

#### M0_NC_ONLINE
- Received by Hare from every Motr process on successfull completion of SNS rebalance operation on a device.
- Hare MUST broadcast M0_NC_ONLINE to all Motr processes on receiving completion of SNS rebalance from all the Motr processes.

#### SNS operation status
- Hare MUST handle SNS operation status request event and broadcast [CM_OP_REPAIR/REBALANCE_STATUS](https://github.com/Seagate/cortx-motr/blob/dev/cm/repreb/cm.h) requests to Motr processes.
- Hare MUST report SNS operation status per Motr process.

#### SNS operation ABORT/PAUSE/RESUME
- Hare MUST handle SNS operation ABORT, PAUSE and RESUME requests by broadcasting the respective event to all Motr processes and handle corresponding responses.
