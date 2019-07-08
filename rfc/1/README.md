---
domain: gitlab.mero.colo.seagate.com
shortname: 1/EPS
name: Entrypoint Server
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
---

## Entrypoint Server

![eps](eps.png)

### Operation

* Start **m0ham** in "listen" mode.
* **m0d** sends entrypoint request to **m0ham** via ha-link (1).
* **m0ham**'s entrypoint request handler makes `popen("get-entrypoint")` call (2).
* **get-entrypoint** is a "curl | awk | m0hagen" pipeline:
  - `curl` commands get entrypoint data from Consul (3) and output it to stdout (4);
  - `awk` reformats that data into YAML representation of `m0_ha_entrypoint_rep` (5);
  - **m0hagen** converts that to xcode string.
* **m0ham** reads the output of `popen()` and passes it to `m0_xcode_read()`, which constructs `m0_ha_entrypoint_rep` object.
* **m0ham** sends `m0_ha_entrypoint_rep` back to the **m0d** via ha-link.

### Querying Consul for Entrypoint Data

* List of confd services:
  ```bash
  $ curl -sX GET http://localhost:8500/v1/catalog/service/confd | jq -r '.[] | "\(.Node) \(.ServiceAddress):\(.ServicePort)"'
  node1 192.168.180.162@tcp:12345:44:101
  node2 192.168.180.166@tcp:12345:44:101
  ```
* Principal RM is co-located with the RC Leader:
  ```bash
  # get session id from the "leader" key
  SID=$(consul kv get -detailed leader | awk '/Session/ {print $2}')
  # use session id to find the leader
  curl -sX GET http://localhost:8500/v1/session/info/$SID | jq -r '.[].Node'
  ```
