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

### EVENT: data disk fails

REACTION: Device failures are implicitly handled by the hardware.

### [post-EES] EVENT: data disk fails

DETECTED BY: `m0d` (Mero IO service) or SSPL

REACTION: `m0d` or SSPL sends "device failure" message to `hax`.

CHAIN REACTION:
- `hax` updates state of the corresponding device in the Consul KV.
- Consul watch handler (provided by Hare) broadcasts HA state update
  ("device D is now FAILED") to all `hax` processes.
- `hax`es pass HA state updates to the connected Mero processes.

Consul watch handler can also perform other actions, e.g., run `smartctl`.

### EVENT: IOS crashes

DETECTED BY: Consul health check (e.g. `pgrep`,
`systemctl status <service-name>`)

REACTION: State of the corresponding Consul service changes to "failed".

CHAIN REACTION:
- Consul service is being watched.  The watch handler notifies Pacemaker.
- Pacemaker tries to restart the service or
  [~~nukes the entire site from orbit~~](https://www.youtube.com/watch?v=aCbfMkh940Q)
  performs failover.

[post-EES] CHAIN REACTION:
- Consul service is being watched.  The watch handler broadcasts
  HTTP POST request to all `hax` processes.
- The `hax` that is connected to the failed `m0d` closes ha-link to it.
- `hax` processes send HA state updates to all Mero processes in the cluster.

### EVENT: confd crashes

DETECTED BY: Consul health check (e.g. `systemctl status <service-name>`)

REACTION: Consul service state changes, triggering the watch that
monitors this service.

CHAIN REACTION:
- Consul service watch sends HTTP POST request to `hax`.
- `hax` sends notification to the linked Mero processes.
- Hare RC leader which is co-located with the confd will be re-elected
  as confd restarts.

### EVENT: `hax` crashes

DETECTED BY: systemd

REACTION:
- systemd restarts hax service ..
- .. and m0d services &mdash; they are defined in systemd scripts as
  dependent on hax.

[post-EES] REACTION:
- systemd restarts hax service, hax notifies Mero processes and re-establishes
  connections without restarting Mero services.

### EVENT: S3 server crashes

DETECTED BY: Consul health check

REACTION: Consul [watch handler](https://www.consul.io/docs/agent/watches.html#handlers)
restarts the S3 server.

### EVENT: Mero client crashes

XXX

### EVENT: `consul` agent is not accessible

XXX

### EVENT: `hax` gets error when sending message to Mero process

DETECTED BY: `hax`

REACTION: `hax` logs an error.

### EVENT: node crashes

DETECTED BY: Consul

REACTION: Consul node state changes.

CHAIN REACTION: Pacemaker, which is polling nodes' state information
from the Consul, learns about the node crash and does the failover.
