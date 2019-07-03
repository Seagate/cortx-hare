---
domain: gitlab.mero.colo.seagate.com
shortname: 1/EPS
name: Entrypoint Server
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
---

## eps: Entrypoint Server

![eps](eps.png)

### Data flow

1. `m0d` sends entrypoint request to `eps` via ha-link.
2. `eps` gets entrypoint reply data from the Consul KV store:
   * list on confd services -- from `consul catalog nodes -service=confd`
   * principal RM is co-located with the RC leader node:
     ```bash
     # get session id from the "leader" key
     consul kv get -detailed -recurse leader/ | grep Session
     # use session id to find the leader
     curl -sX GET http://localhost:8500/v1/session/info/<session-id> | jq -r '.[].Node'
     ```
3. `eps` sends entrypoint reply to `eps` via ha-link.
