<!--
  Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  For any questions about this software or licensing,
  please email opensource@seagate.com or cortx-questions@seagate.com.
-->

---
domain: gitlab.mero.colo.seagate.com
shortname: 11/HCTL
name: Hare Controller CLI
status: stable
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

```sh
hctl node [OPTIONS] COMMAND [ARGS]...

Options:
  --verbose
  --username TEXT
  --password TEXT
  --help           Show this message and exit.

Commands:
  maintenance    Switch the cluster to maintenance mode.
  shutdown       Shutdown (power off) the node by name.
  standby        Put the given node into standby mode.
  status         Show status of all cluster nodes.
  unmaintenance  Move the cluster from maintenance back to normal mode.
  unstandby      Remove the given node from standby mode.
```

#### General conventions

1. In case of an error exitcode, the caller should consider `stderr` for explanatory text.
2. `hctl node status` produces the output to `stdout` in case of success exit code. The output is a valid JSON object.
3. All log messages are produced to `stderr` and duplicated to journald logs.

#### General options

* `--verbose` Show debug logging while executing any command.
* `--username` and `--password` Current linux user credentials to authenticate in `pcsd` Pacemaker daemon. These parameters can be helpful when the command is executed from a non-root user. This pair of options is optional; when omitted, no local authentication will be issued while communicating to Pacemaker.

#### Commands

##### maintenance

```sh
Usage: hctl node maintenance [OPTIONS]

  Switch the cluster to maintenance mode.

Options:
  --all                  [required]
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Put the whole cluster into so called 'smart maintenance' mode. This mode includes the following sequence:

1. Disable STONITH resources. Wait until these resources are stopped (no longer than `timeout-sec` seconds).
2. Put all the nodes to 'standby' mode. Wait until all resources are stopped (no longer than `timeout-sec` seconds).

**Note:** If any of the steps fail, the cluster will remain in an unstable state: if STONITH resources are disabled, split-brain becomes a real risk. The user will need to issue `hctl node unmaintenance --all` manually to return the cluster back to normal state (note that this command can lead to fencing).

##### shutdown

```sh
Usage: hctl node shutdown [OPTIONS] NODE

  Shutdown (power off) the node by name.

Options:
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Shuts the given node down via IPMI interface (the corresponding IPMI address and credentials are taken from Pacemaker's STONITH resources). Shutdown procedure contains two steps:

1. Switch the node to standby (so that all the resources get stopped for sure)
2. Once all resources are stopped, trigger shutdown.

**Notes:**

1. Item \[1] waits until all the resources are stopped for sure. It waits no more than `timeout-sec` seconds. Once timeout is exceeded, the tool exits with an exception and non-zero exit code.
2. As a result, if the resources take too much time to shutdown (by any reason), shutdown will not happen but the node will remain in 'standby' mode. The user will need to 'unstandby' the node manually in this case.
3. If shutdown fails (e.g. due to IPMI failure), the node will also remain in 'standby' mode.

##### standby

```sh
Usage: hctl node standby [OPTIONS] [NODE]

  Put the given node into standby mode.

Options:
  --all   Put all the nodes in the cluster to standby mode (no node name is
          required).

  --help  Show this message and exit.
```

Put the given node into standby mode. Note that the tool DOES NOT wait until all the resources are stopped at the given node and exits early.

##### status

```sh
Usage: hctl node status [OPTIONS]

  Show status of all cluster nodes.

Options:
  --full  Show overall cluster status, so not only nodes will be included.
  --help  Show this message and exit.
```

Outputs the status of the nodes in JSON format. Sample outputs are as follows:

```sh
hctl node status --full
{"resources": {"statistics": {"started": 6, "stopped": 0, "starting": 0}}, "nodes": [{"name": "smc7-m11", "online": true, "standby": false, "unclean": false, "resources_running": 3}, {"name": "smc8-m11", "online": false, "standby": false, "unclean": false, "resources_running": 3}]}
```

```sh
hctl node status
[{"name": "smc7-m11", "online": true, "standby": false, "unclean": false, "resources_running": 3}, {"name": "smc8-m11", "online": false, "standby": false, "unclean": false, "resources_running": 3}]
```

##### unmaintenance

```sh
Usage: hctl node unmaintenance [OPTIONS]

  Move the cluster from maintenance back to normal mode.

Options:
  --all                  [required]
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Recover from 'smart maintenance' mode. Includes the following steps:

1. Revoke all the nodes from 'standby' mode. Wait until all resources are stopped (no longer than `timeout-sec` seconds).
2. Enable STONITH resources. Wait until these resources are running (no longer than `timeout-sec` seconds).

**Note:** This command can be used as a general way to return the cluster back to normal mode (so it can 'cure' the cluster after 'standby --all' or after an unsuccessful shutdown).

##### unstandby

```sh
Usage: hctl node unstandby [OPTIONS] [NODE]

  Remove the given node from standby mode.

Options:
  --all   Remove all the nodes in the cluster from standby mode (no node name
          is required).

  --help  Show this message and exit.
```

**Note:** Similarly to `hctl node standby`, this command exits early, i.e. it doesn't wait until the resources are started at the nodes that used to be in standby state.
