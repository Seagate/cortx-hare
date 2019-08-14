---
domain: gitlab.mero.colo.seagate.com
shortname: 7/FAIL
name: Failure Handling
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Failure Handling

* EVENT: IOS crashes

  DETECTED BY: Consul watch

  REACTION: Watch handler updates the KV: sets the value of key
  `processes/<fid>` to `{ "state": "failed" }`.

  CHAIN REACTION (EES): `processes/` key prefix is being watched.
  The watch handler notifies Pacemaker, which
  [~~nukes the entire site from orbit~~](https://www.youtube.com/watch?v=aCbfMkh940Q)
  performs failover.

  CHAIN REACTION (POST-EES):

  1. `processes/` key prefix is being watched.  The watch handler
     broadcasts HTTP POST request to all `hax` processes.

  1. `hax` processes send HA state update to Mero processes.

* EVENT: confd crashes

  DETECTED BY: Consul watch

  REACTION: XXX TBD

* EVENT: hax crashes

  DETECTED BY: Consul watch

  REACTION: XXX TBD

* EVENT: consul agent is not accessible

  XXX

* EVENT: hax gets error when sending message to Mero process

  XXX

* EVENT: Mero client crashes

  XXX

* XXX
