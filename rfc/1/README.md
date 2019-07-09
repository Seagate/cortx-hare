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

* **get-entrypoint** gets entrypoint data from Consul and converts it to `m0_ha_entrypoint_rep` in xcode string format.
  Possible implementation:
  - `curl` gets entrypoint data from Consul (3) and writes it to stdout (4);
  - `awk` reformats that data into YAML representation of `m0_ha_entrypoint_rep` (5);
  - **m0hagen** converts that to xcode string.

  Alternatively, `awk` (or whichever tool is used) can output xcode string directly, without calling **m0hagen**.

* **m0ham** reads the output of `popen()` and passes it to `m0_xcode_read()`, which constructs `m0_ha_entrypoint_rep` object.

* **m0ham** sends `m0_ha_entrypoint_rep` back to the **m0d** via ha-link.

### References

* [`get-entrypoint`](../../get-entrypoint)
