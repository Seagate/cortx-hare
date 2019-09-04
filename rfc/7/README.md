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
- `hax` processes send HA state update to Mero processes.

### EVENT: confd crashes

DETECTED BY: Consul health check (e.g. `systemctl status <service-name>`)

REACTION: Consul service state changes, triggering the watch that
monitors this service.

CHAIN REACTION:
- Consul service watch sends HTTP POST request to `hax`.
- `hax` sends notification to the linked Mero processes.

### EVENT: `hax` crashes

DETECTED BY: systemd/Pacemaker

REACTION: systemd/Pacemaker tries to restart hax service.

### EVENT: `consul` agent is not accessible

XXX

### EVENT: `hax` gets error when sending message to Mero process

XXX

### EVENT: Mero client crashes

XXX
