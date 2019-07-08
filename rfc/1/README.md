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
2. `eps` gets entrypoint reply data from Consul:
   * list of confd services, example:
     ```bash
     $ curl -sX GET http://localhost:8500/v1/catalog/service/confd | jq -r '.[] | "\(.Node) \(.ServiceAddress):\(.ServicePort)"'
     node1 192.168.180.162@tcp:12345:44:101
     node2 192.168.180.166@tcp:12345:44:101
     ```
   * principal RM is co-located with the RC Leader:
     ```bash
     # get session id from the "leader" key
     SID=`consul kv get -detailed leader | awk '/Session/ {print $2}'`
     # use session id to find the leader
     curl -sX GET http://localhost:8500/v1/session/info/$SID | jq -r '.[].Node'
     ```
3. `eps` sends entrypoint reply to `eps` via ha-link.

### `m0ham`, `get-entrypoint`

- Start m0ham in "listen" mode.
- m0d sends entrypoint request to m0ham.
- m0ham's entrypoint request handler makes `popen("get-entrypoint")` call.
- `get-entrypoint` is a simple bash pipeline:
  ```bash
  curl ... | awk ... | m0hagen
  ```
  - curl queries Consul;
  - awk converts curl's output to an entrypoint reply in YAML format;
  - m0hagen converts that to xcode string.
- m0ham reads the output of popen() and passes it to `m0_xcode_read()`, which builds `m0_ha_entrypoint_rep` object.
- m0ham sends `m0_ha_entrypoint_rep` back to the m0d.
