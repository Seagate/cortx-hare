---
domain: gitlab.mero.colo.seagate.com
shortname: 11/HCTL
name: Hare Controller CLI
status: raw
editor: Konstantin Nekrasov <konstantin.nekrasov@seagate.com>
---

## Abstract

`hctl` is a command-line interface (extensible set of utilities) to manage Hare cluster.

## Use cases

### Hare cluster bootstrap

TBD

### Hare cluster shutdown

TBD

### Hare cluster status

TBD

### Node management

General command structure is as follows:

```
hctl node <command>
```
Detailed list of commands can be seen below.

|#|Use case|Command line|Sample output|
|-|--------|------------|-------------|
|1|Stop the node ('standby')|`hctl node standby <node-id>`| |
|2|Start the node ('unstandby')|`hctl node unstandby <node-id>`| |
|3|Stop all nodes in cluster ('standby all')|`hctl node standby --all`| |
|4|Start all nodes in cluster ('unstandby all')|`hctl node unstandby --all`| |
|5|Shutdown a node|`hctl node shutdown <node-id>`| |
|6|Get the status of all nodes in the cluster|`hctl node status`| `[{"name": "srvnode-1", "online": false, "shutdown": false, "standby": true, "unclean": false, "resources_running": 0}]` |
|7|Enable "smart maintenance" mode |`hctl node --verbose maintenance --all --timeout-sec=120`| |
|8|Disable "smart maintenance" mode |`hctl node --verbose unmaintenance --all --timeout-sec=120`| |

**Notes**
1. Smart maintenance - combination of two steps:
   - Disabling STONITH resources
   - Switching both cluster nodes to standby mode
2. `hctl node maintenance --all` command guarantees that once it finishes, the whole operation either succeeded or failed. The caller must analyze exit code.
3. In case of failure while switching to "smart maintenance", the Pacemaker cluster will be left in unstable state. The caller must perform all the actions to log the problem, reporting it via UI etc but then it MUST run `hctl node unmaintenance --all` to switch the cluster back to normal mode. Note that this operation will most probably trigger STONITH'ing.
4. `hctl node unmaintenance --all` must be also called in successful case when the maintenance works are over.

**General conventions**:
1. In case of an error exitcode, the caller should consider `stderr` for explanatory text.
2. `hctl node status` produces the output to `stdout` in case of success exit code. The output is a valid JSON object.
3. All log messages are produced to `stderr`.
