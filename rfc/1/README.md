---
domain: gitlab.mero.colo.seagate.com
shortname: 1/EPS
name: Entrypoint Server
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## eps: Entrypoint Server

![eps](eps.png)

### Data flow

1. `m0d` sends entrypoint request to `eps` via ha-link.
2. `eps` gets entrypoint reply data from the "entrypoint" key in Consul KV.
3. `eps` sends entrypoint reply to `eps` via ha-link.
