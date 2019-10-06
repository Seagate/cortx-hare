---
domain: gitlab.mero.colo.seagate.com
shortname: 7/FAIL
name: Failure Handling
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Mandar Sawant <mandar.sawant@seagate.com>
---

## Failure Handling

### EVENT: IOS disk failure

REACTION (EES):
Device failures are implicitly handled by the hardware for EES. So Consul-kv need not
maintain device hierarchy and corresponding states.

REACTION (POST-EES): State of the corresponding device is updated in consul-kv.

CHAIN REACTION (POST-EES):
- Mero disks are added to consul-kv.
- Disk Failure is reported to hax by Mero or by SSPL.
- Hax updates the corresponding disk state in consul-kv.
- Hare takes relevant action, e.g. trigger smartctl tests or notify cluster about disk failure.

### EVENT: IOS crashes

DETECTED BY: Consul health check (e.g. `pgrep`,
`systemctl status <service-name>`)

REACTION: State of the corresponding Consul service changes to "failed".

CHAIN REACTION (EES):
- Consul service is being watched.  The watch handler notifies Pacemaker.
- Pacemaker tries to restart the service or
  [~~nukes the entire site from orbit~~](https://www.youtube.com/watch?v=aCbfMkh940Q)
  performs failover.

CHAIN REACTION (POST-EES):
- Consul service is being watched.  The watch handler broadcasts
  HTTP POST request to all `hax` processes.
- `hax` processes send HA state updates to all Mero processes in the cluster.
- Hax disconnects Ha links with the corresponding process, re-establishes as
  the process comes back online.

### EVENT: confd crashes

DETECTED BY: Consul health check (e.g. `systemctl status <service-name>`)

REACTION: Consul service state changes, triggering the watch that
monitors this service.

CHAIN REACTION (EES):
- Consul service watch sends HTTP POST request to `hax`.
- `hax` sends notification to the linked Mero processes.
- Hare RC leader which is co-located with the confd will be re-elected
  as confd restarts.

### EVENT: `hax` crashes

DETECTED BY: systemd

REACTION (EES):
- systemd restarts hax service ..
- .. and m0d services &mdash; they are defined in systemd scripts as
  dependent on hax.

REACTION (POST-EES):
- systemd restarts hax service, hax notifies Mero processes and re-establishes
  connections without restarting Mero services.

### EVENT: node crashes

DETECTED BY: Consul

REACTION: Consul node state changes.

CHAIN REACTION: Pacemaker, which is polling nodes' state information from the Consul,
learns about the node crash and does the failover.

### EVENT: `consul` agent is not accessible

XXX

### EVENT: `hax` gets error when sending message to Mero process

DETECTED BY: hax

REACTION (EES):
- Hax logs an error.

### EVENT: Mero client crashes

XXX
