---
domain: gitlab.mero.colo.seagate.com
shortname: 7/FAIL
name: Failure Handling
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Failure Handling

* EVENT: IOS crashes

  DETECTED BY: Consul health check (e.g., `pgrep`, `systemctl status <service-name>`)

  REACTION: Based on consul health check output, consul service (mero process, i.e.
  confd, ios) state is updated.

  CHAIN REACTION (EES): Consul service is being watched.
  The watch handler notifies Pacemaker, which tries to restart the service or
  [~~nukes the entire site from orbit~~](https://www.youtube.com/watch?v=aCbfMkh940Q)
  performs failover.

  CHAIN REACTION (POST-EES):

  1. Consul service is being watched.  The watch handler broadcasts HTTP POST request
  to all `hax` processes.

  2. `hax` processes sends HA state update to Mero processes.

* EVENT: confd crashes

  DETECTED BY: Consul health check (e.g. `systemctl status <service-name>`)

  REACTION: Consul service is being watched. Based on health checker output, Consul
  service state is updated which triggers the corresponding watcher.

  CHAIN REACTION: Consul service watcher, notifies hax which notifies Mero nodes
  about the mero process's state change.

* EVENT: hax crashes

  DETECTED BY: systemd/pacemaker

  REACTION: systemd/pacemaker tries to restart hax service.

* EVENT: consul agent is not accessible

  XXX

* EVENT: hax gets error when sending message to Mero process

  XXX

* EVENT: Mero client crashes

  XXX

* XXX
