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
|1|Stop the node ('standby')|`hctl node standby <node-name>`| |
|2|Start the node ('unstandby')|`hctl node unstandby <node-name>`| |
|3|Stop all nodes in cluster ('standby all')|`hctl node standby --all`| |
|4|Start all nodes in cluster ('unstandby all')|`hctl node unstandby --all`| |
|5|Shutdown a node|`hctl node shutdown <node-name>`| |
|6|Turn on a node|`hctl node turn-on <node-name>`| |
|7|Get the status of all nodes in the cluster|`hctl node status`|`[{"name":"ssc-vm-0018", "online":true, "standby":false, "shutdown":false}, {"name":"ssc-vm-0019", "online":true, "standby":true, "shutdown":false}]`|


***General conventions***:
1. In case of an error exitcode, the caller should consider `stderr` for explanatory text.
2. `hctl node status` produces the output to `stdout` in case of success exit code. The output is a valid JSON object.
