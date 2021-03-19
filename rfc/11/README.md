---
domain: github.com
shortname: 11/HCTL
name: Hare Controller CLI
status: stable
editor: Mandar Sawant <mandar.sawant@seagate.com>
contributors:
  - Konstantin Nekrasov <konstantin.nekrasov@seagate.com>
---

`hctl` is a command-line interface for managing Hare cluster.

```
$ hctl --help
Usage: hctl <command> [options]

Interact with Motr cluster.

Commands:

    bootstrap   bootstrap the cluster
    node        manage the cluster nodes
    reportbug   gather Hare forensic data
    shutdown    stop the cluster
    start       start cluster
    status      show cluster status

    help        Show this help and exit.
```

## Cluster bootstrap

```
$ hctl bootstrap --help
Usage: hare-bootstrap [<option>]... <CDF>
       hare-bootstrap [<option>]... --conf-dir <dir>

Bootstrap the cluster.

Positional arguments:
  <CDF>                  Path to the cluster description file.
  -c, --conf-dir <dir>   Don't generate configuration files, use existing
                         ones from the specified directory.

Options:
  --debug      Print commands and their arguments as they are executed.
  --mkfs       Execute m0mkfs.  *CAUTION* This wipes all Motr data!
  -h, --help   Show this help and exit.
```

Initial bootstrap requires `--mkfs`.  Subsequent `hctl bootstrap` calls SHOULD NOT use `--mkfs`, otherwise any data stored in Motr will be lost.
```
$ hctl bootstrap --mkfs /tmp/ldr1-cluster.yaml
2020-09-03 09:54:39: Generating cluster configuration... OK
2020-09-03 09:54:40: Starting Consul server agent on this node........... OK
2020-09-03 09:54:49: Importing configuration into the KV store... OK
2020-09-03 09:54:49: Starting Consul agents on other cluster nodes... OK
2020-09-03 09:54:50: Updating Consul agents configs from the KV store... OK
2020-09-03 09:54:51: Installing Motr configuration files... OK
2020-09-03 09:54:51: Waiting for the RC Leader to get elected........... OK
2020-09-03 09:55:00: Starting Motr (phase1, mkfs)... OK
2020-09-03 09:55:06: Starting Motr (phase1, m0d)... OK
2020-09-03 09:55:09: Starting Motr (phase2, mkfs)... OK
2020-09-03 09:55:16: Starting Motr (phase2, m0d)... OK
2020-09-03 09:55:19: Checking health of services... OK
```

## Cluster shutdown

```
$ hctl shutdown
Stopping m0d@0x7200000000000001:0xc (ios) at ssc-vm-c-0552.colo.seagate.com...
Stopping m0d@0x7200000000000001:0x29 (ios) at ssc-vm-c-0553.colo.seagate.com...
Stopped m0d@0x7200000000000001:0xc (ios) at ssc-vm-c-0552.colo.seagate.com
Stopped m0d@0x7200000000000001:0x29 (ios) at ssc-vm-c-0553.colo.seagate.com
Stopping m0d@0x7200000000000001:0x9 (confd) at ssc-vm-c-0552.colo.seagate.com...
Stopping m0d@0x7200000000000001:0x26 (confd) at ssc-vm-c-0553.colo.seagate.com...
Stopped m0d@0x7200000000000001:0x26 (confd) at ssc-vm-c-0553.colo.seagate.com
Stopped m0d@0x7200000000000001:0x9 (confd) at ssc-vm-c-0552.colo.seagate.com
Stopping hare-hax at ssc-vm-c-0552.colo.seagate.com...
Stopping hare-hax at ssc-vm-c-0553.colo.seagate.com...
Stopped hare-hax at ssc-vm-c-0552.colo.seagate.com
Stopped hare-hax at ssc-vm-c-0553.colo.seagate.com
Stopping hare-consul-agent at ssc-vm-c-0552.colo.seagate.com...
Stopping hare-consul-agent at ssc-vm-c-0553.colo.seagate.com...
Stopped hare-consul-agent at ssc-vm-c-0552.colo.seagate.com
Stopped hare-consul-agent at ssc-vm-c-0553.colo.seagate.com
Killing RC Leader at ssc-vm-c-0552.colo.seagate.com... **ERROR**
```

### Cluster shutdown --node
#### Stops Hare, Motr and Consul processes on the local node only

```
$ hctl shutdown --node
Stopping m0d@0x7200000000000001:0x30 (ios) at ssc-vm-2090.colo.seagate.com...
Stopped m0d@0x7200000000000001:0x30 (ios) at ssc-vm-2090.colo.seagate.com
Stopping m0d@0x7200000000000001:0x2d (confd) at ssc-vm-2090.colo.seagate.com...
Stopped m0d@0x7200000000000001:0x2d (confd) at ssc-vm-2090.colo.seagate.com
Stopping hare-hax at ssc-vm-2090.colo.seagate.com...
Stopped hare-hax at ssc-vm-2090.colo.seagate.com
Stopping hare-consul-agent at ssc-vm-2090.colo.seagate.com...
Stopped hare-consul-agent at ssc-vm-2090.colo.seagate.com
```

## Cluster start

```
$ hctl start
2020-09-18 06:59:59: Starting Consul server agent on this node............ OK
2020-09-18 07:00:09: Importing configuration into the KV store... OK
2020-09-18 07:00:09: Starting Consul agents on other cluster nodes... OK
2020-09-18 07:00:09: Updating Consul agents configs from the KV store... OK
2020-09-18 07:00:10: Installing Motr configuration files... OK
2020-09-18 07:00:10: Waiting for the RC Leader to get elected..... OK
2020-09-18 07:00:12: Starting Motr (phase1, m0d)... OK
2020-09-18 07:00:15: Starting Motr (phase2, m0d)... OK
2020-09-18 07:00:18: Checking health of services... OK
```

### Cluster start --node
#### Starts Hare, Motr and Consul processes on the current node only

```
$ hctl start --node
2021-02-19 05:11:04: Starting Consul agent on this node.... OK
2021-02-19 05:11:05: Starting Motr (phase1, m0d)... OK
2021-02-19 05:11:09: Starting Motr (phase2, m0d)... OK
2021-02-19 05:11:12: Checking health of services... OK
OK
```

## Cluster status

```
$ hctl status --help
usage: hare-status [OPTION]

Show cluster status.

optional arguments:
  -h, --help  show this help message and exit
  --json      show output in JSON format
```

```
$ hctl status
Data pools:
    # fid name
    0x6f00000000000001:0x2e 'tier1-ssd'
    0x6f00000000000001:0x39 'tier2-hdd'
Profiles:
    # fid name: pool(s)
    0x7000000000000001:0x54 'fast': 'tier1-ssd'
    0x7000000000000001:0x55 'slow': 'tier2-hdd'
    0x7000000000000001:0x56 'both': 'tier1-ssd' 'tier2-hdd'
Services:
    localhost  (RC)
    [started]  hax        0x7200000000000001:0x6   172.28.128.45@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x9   172.28.128.45@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0xc   172.28.128.45@tcp:12345:2:2
    [unknown]  m0_client  0x7200000000000001:0x28  172.28.128.45@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x2b  172.28.128.45@tcp:12345:4:2
```

```
$ hctl status --json
{
  "pools": [
    {
      "fid": "0x6f00000000000001:0x2e",
      "name": "tier1-ssd"
    },
    {
      "fid": "0x6f00000000000001:0x39",
      "name": "tier2-hdd"
    }
  ],
  "profiles": [
    {
      "fid": "0x7000000000000001:0x54",
      "name": "fast",
      "pools": [
        "tier1-ssd"
      ]
    },
    {
      "fid": "0x7000000000000001:0x55",
      "name": "slow",
      "pools": [
        "tier2-hdd"
      ]
    },
    {
      "fid": "0x7000000000000001:0x56",
      "name": "both",
      "pools": [
        "tier1-ssd",
        "tier2-hdd"
      ]
    }
  ],
  "filesystem": {
    "stats": {
      "fs_free_seg": 8590389096,
      "fs_total_seg": 8590951472,
      "fs_free_disk": 104689827840,
      "fs_avail_disk": 104689827840,
      "fs_total_disk": 104689827840,
      "fs_svc_total": 2,
      "fs_svc_replied": 2
    },
    "timestamp": 1602613220.761281,
    "date": "2020-10-13T18:20:20.761281"
  },
  "nodes": [
    {
      "name": "localhost",
      "svcs": [
        {
          "name": "hax",
          "fid": "0x7200000000000001:0x6",
          "ep": "172.28.128.45@tcp:12345:1:1",
          "status": "started"
        },
        {
          "name": "confd",
          "fid": "0x7200000000000001:0x9",
          "ep": "172.28.128.45@tcp:12345:2:1",
          "status": "started"
        },
        {
          "name": "ioservice",
          "fid": "0x7200000000000001:0xc",
          "ep": "172.28.128.45@tcp:12345:2:2",
          "status": "started"
        },
        {
          "name": "m0_client",
          "fid": "0x7200000000000001:0x28",
          "ep": "172.28.128.45@tcp:12345:4:1",
          "status": "unknown"
        },
        {
          "name": "m0_client",
          "fid": "0x7200000000000001:0x2b",
          "ep": "172.28.128.45@tcp:12345:4:2",
          "status": "unknown"
        }
      ]
    }
  ]
}
```

## Fetch FIDs
### Fetches the fids for services configured on a node
This script fetches fids of motr and s3 services of a node from `consul-kv.json` generated by cfgen, and displays it using `hctl fetch-fids` utility.

Note: Currently the script can run only from the node running bootstrap command.

```
$ hctl fetch-fids --help
usage: hare-fetch-fids [OPTION]

Fetches the fids for services configured on a node.

optional arguments:
  -h, --help            show this help message and exit
  --service SERVICE, -s SERVICE
                        service name. - Returns fid for given service. List of
                        services- "confd", "ioservice", "s3server". Default:
                        Returns the fids for all the services.
  --node NODE, -n NODE  node-name - Returns the fids of services for the given
                        node. Default: Local node
  --all                 Returns fids of all the services for nodes in cluster.

```

Usage: `hctl fetch-fids [-s <service-name>] [-n <node-name>] [--all]`

Fetches fid for a particular service on a particular node.
```
$ hctl fetch-fids -s ioservice -n ssc-vm-c-1813.colo.seagate.com
0x7200000000000001:0xc
```
Fetch fids for all the services for nodes in cluster.
```
$ hctl fetch-fids --all
[
  {
    "name": "ssc-vm-c-1813.colo.seagate.com",
    "svcs": [
      {
        "name": "confd",
        "fid": "0x7200000000000001:0x9"
      },
      {
        "name": "ioservice",
        "fid": "0x7200000000000001:0xc"
      }
    ]
  },
  {
    "name": "ssc-vm-c-1898.colo.seagate.com",
    "svcs": [
      {
        "name": "confd",
        "fid": "0x7200000000000001:0x35"
      },
      {
        "name": "ioservice",
        "fid": "0x7200000000000001:0x38"
      }
    ]
  }
]

```

Fetch fids of all the services on a node. 
```
$ hctl fetch-fids -n ssc-vm-c-1813.colo.seagate.com
{
  "name": "ssc-vm-c-1813.colo.seagate.com",
  "svcs": [
    {
      "name": "confd",
      "fid": "0x7200000000000001:0x9"
    },
    {
      "name": "ioservice",
      "fid": "0x7200000000000001:0xc"
    }
  ]
}
```

## Node management

```
$ hctl node --help
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

**Note:** error messages are sent to stderr and duplicated to journald logs.

* Use `--username` and `--password` current Linux user credentials to authenticate in `pcsd` Pacemaker daemon.  These parameters can be helpful when the command is executed by a non-root user.  This pair of options is optional; when omitted, no local authentication will be issued while communicating to Pacemaker.

### hctl-node subcommands

#### hctl node maintenance

```
Usage: hctl node maintenance [OPTIONS]

  Switch the cluster to maintenance mode.

Options:
  --all                  [required]
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Puts the cluster into "smart maintenance" mode.  This mode includes the following sequence:

1. Disable STONITH resources. Wait until these resources are stopped (no longer than `timeout-sec` seconds).
2. Put all the nodes to 'standby' mode. Wait until all resources are stopped (no longer than `timeout-sec` seconds).

**Note:** If any of the steps fail, the cluster will remain in an unstable state: if STONITH resources are disabled, split-brain becomes a real risk. The user will need to issue `hctl node unmaintenance --all` manually to return the cluster back to normal state (note that this command can lead to fencing).

#### hctl node shutdown

```
Usage: hctl node shutdown [OPTIONS] NODE

  Shutdown (power off) the node by name.

Options:
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Powers off the node via IPMI interface (the corresponding IPMI address and credentials are taken from Pacemaker's STONITH resources).  Shutdown procedure:

1. Switch the node to standby (so that all the resources get stopped for sure)
2. Once all resources are stopped, trigger shutdown.

**Notes:**

1. Item \[1] waits until all the resources are stopped for sure. It waits no more than `timeout-sec` seconds. Once timeout is exceeded, the tool exits with an exception and non-zero exit code.
2. As a result, if the resources take too much time to shutdown (by any reason), shutdown will not happen but the node will remain in 'standby' mode. The user will need to 'unstandby' the node manually in this case.
3. If shutdown fails (e.g. due to IPMI failure), the node will also remain in 'standby' mode.

#### hctl node standby

```
Usage: hctl node standby [OPTIONS] [NODE]

  Put the given node into standby mode.

Options:
  --all   Put all the nodes in the cluster to standby mode (no node name is
          required).

  --help  Show this message and exit.
```

Puts the node into standby mode.  Note that the tool DOES NOT wait until all the resources are stopped at the given node and exits early.

#### hctl node status

```
Usage: hctl node status [OPTIONS]

  Show status of all cluster nodes.

Options:
  --full  Show overall cluster status, so not only nodes will be included.
  --help  Show this message and exit.
```

Outputs status of cluster nodes in JSON format.  Sample output:
```
$ hctl node status
[{"name": "smc7-m11", "online": true, "standby": false, "unclean": false, "resources_running": 3}, {"name": "smc8-m11", "online": false, "standby": false, "unclean": false, "resources_running": 3}]
```
```
$ hctl node status --full
{"resources": {"statistics": {"started": 6, "stopped": 0, "starting": 0}}, "nodes": [{"name": "smc7-m11", "online": true, "standby": false, "unclean": false, "resources_running": 3}, {"name": "smc8-m11", "online": false, "standby": false, "unclean": false, "resources_running": 3}]}
```

#### hctl node unmaintenance

```
Usage: hctl node unmaintenance [OPTIONS]

  Move the cluster from maintenance back to normal mode.

Options:
  --all                  [required]
  --timeout-sec INTEGER  Maximum time that this command will wait for any
                         operation to complete before raising an error

  --help                 Show this message and exit.
```

Disables "smart maintenance" mode.  Steps:

1. Revoke all the nodes from 'standby' mode. Wait until all resources are stopped (no longer than `timeout-sec` seconds).
2. Enable STONITH resources. Wait until these resources are running (no longer than `timeout-sec` seconds).

**Note:** This command can be used as a general way to return the cluster back to normal mode (so it can 'cure' the cluster after 'standby --all' or after an unsuccessful shutdown).

#### hctl node unstandby

```
Usage: hctl node unstandby [OPTIONS] [NODE]

  Remove the given node from standby mode.

Options:
  --all   Remove all the nodes in the cluster from standby mode (no node name
          is required).

  --help  Show this message and exit.
```

**Note:** Similarly to `hctl node standby`, this command exits early, i.e. it doesn't wait until the resources are started at the nodes that used to be in standby state.

#### hctl node-join

Use this command to start Hare and Motr services on a node that was rebooted.

```
[root@ssc-vm-c-0552 cortx-hare]# hctl node-join --help
Usage: hare-node-join [<option>]... <CDF>
       hare-node-join [<option>]... --conf-dir <dir>

Start and join a node with the cluster.

Positional arguments:
  <CDF>                        Path to the cluster description file.
  -c, --conf-dir <dir>         Don't generate configuration files, use existing
                               ones from the specified directory.
  --conf-create                Re-create configuration on this node.
  --consul-addr  <consul-addr> Active Consul server address.
  --consul-port  <consul-port> Active Consul server port.
Options:
  -h, --help    Show this help and exit.
```

##### Stopped services on a node

```
[root@ssc-vm-c-0553 cortx-hare]# hctl status
Profile: 0x7000000000000001:0x3d
Data pools:
    0x6f00000000000001:0x3e
Services:
    ssc-vm-c-0553.colo.seagate.com  (RC)
    [started]  hax        0x7200000000000001:0x23  192.168.9.107@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x26  192.168.9.107@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0x29  192.168.9.107@tcp:12345:2:2
    [unknown]  m0_client  0x7200000000000001:0x37  192.168.9.107@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x3a  192.168.9.107@tcp:12345:4:2
    ssc-vm-c-0552.colo.seagate.com
    [unknown]  hax        0x7200000000000001:0x6   192.168.9.108@tcp:12345:1:1
    [unknown]  confd      0x7200000000000001:0x9   192.168.9.108@tcp:12345:2:1
    [unknown]  ioservice  0x7200000000000001:0xc   192.168.9.108@tcp:12345:2:2
    [unknown]  m0_client  0x7200000000000001:0x1a  192.168.9.108@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x1d  192.168.9.108@tcp:12345:4:2
```

##### Restarting services on a node without regenerating configuration for the node

```
[root@ssc-vm-c-0552 cortx-hare]# hctl node-join --conf-dir /var/lib/hare --consul-addr 192.168.9.107 --consul-port 8500
2020-09-18 10:10:52: Starting Consul server agent on this node.... OK
2020-09-18 10:10:54: Updating Consul agents configs from the KV store... OK
2020-09-18 10:10:54: Waiting for the RC Leader to get elected... OK
2020-09-18 10:10:55: Starting Motr (phase1, m0d)... OK
2020-09-18 10:10:59: Starting Motr (phase2, m0d)... OK
2020-09-18 10:11:02: Checking health of services... OK
[root@ssc-vm-c-0552 cortx-hare]# hctl status
Profile: 0x7000000000000001:0x3d
Data pools:
    0x6f00000000000001:0x3e
Services:
    ssc-vm-c-0553.colo.seagate.com  (RC)
    [started]  hax        0x7200000000000001:0x23  192.168.9.107@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x26  192.168.9.107@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0x29  192.168.9.107@tcp:12345:2:2
    [unknown]  m0_client  0x7200000000000001:0x37  192.168.9.107@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x3a  192.168.9.107@tcp:12345:4:2
    ssc-vm-c-0552.colo.seagate.com
    [started]  hax        0x7200000000000001:0x6   192.168.9.108@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x9   192.168.9.108@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0xc   192.168.9.108@tcp:12345:2:2
    [unknown]  m0_client  0x7200000000000001:0x1a  192.168.9.108@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x1d  192.168.9.108@tcp:12345:4:2
```

##### hctl node-join with configuration recreate

If a failed node is replaced with a fresh and there's a need to re-generate the configuration files.

```
[root@ssc-vm-c-0552 cortx-hare]# hctl node-join /tmp/ees-cluster.yaml --consul-addr 192.168.9.107 --consul-port 8500 --conf-create
2020-09-18 10:16:52: Generating node configuration... OK
2020-09-18 10:16:52: Starting Consul server agent on this node.... OK
2020-09-18 10:16:53: Updating Consul agents configs from the KV store... OK
2020-09-18 10:16:53: Waiting for the RC Leader to get elected... OK
2020-09-18 10:16:53: Starting Motr (phase1, m0d)... OK
2020-09-18 10:16:58: Starting Motr (phase2, m0d)... OK
2020-09-18 10:17:01: Checking health of services... OK
```

##### hctl node-join with regenerating Hare configuration and Motr mkfs

It is possible that a fresh node needs to run motr mkfs in case the storage was wiped of.
Executing hctl node-join command with `--mkfs` options will re-intialise Motr storage for the given node.

```
[root@ssc-vm-c-0552 cortx-hare]# hctl node-join /tmp/ees-cluster.yaml --consul-addr 192.168.9.107 --consul-port 8500 --mkfs --conf-create
2020-09-18 11:02:32: Generating node configuration... OK
2020-09-18 11:02:33: Starting Consul server agent on this node.... OK
2020-09-18 11:02:35: Updating Consul agents configs from the KV store... OK
2020-09-18 11:02:35: Waiting for the RC Leader to get elected... OK
2020-09-18 11:02:35: Starting Motr (phase1, mkfs)... OK
2020-09-18 11:02:42: Starting Motr (phase1, m0d)... OK
2020-09-18 11:02:45: Starting Motr (phase2, mkfs)... OK
2020-09-18 11:02:52: Starting Motr (phase2, m0d)... OK
2020-09-18 11:02:55: Checking health of services... OK
```
