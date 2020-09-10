# Hare User Guide

## Welcome

Hare is an experiment in
[Social Architecture](https://www.youtube.com/watch?v=uj-li0LO_2g),
disguised as a software project.

## What Hare does?

1. Configures components of the distributed Motr object store.
2. Provides CLI for starting/stopping Motr system.
3. Makes arrangements to ensure that Motr system remains available even
   if some of its components fail.

Hare implementation uses [Consul](https://www.consul.io) key-value store
and health-checking mechanisms.

<!------------------------------------------------------------------->
## Installation

<!-- XXX-TODO
You can download `cortx-hare` RPM from XXX.
-->

To build and install Hare from sources, follow the instructions of [Hare Developer Guide](README_developers.md#installation).

## :ballot_box_with_check: Checklist

Before starting the cluster as \<user\> at \<origin\> machine,
ensure that

\# | Check | Where
--- | --- | ---
1 | passwordless `sudo` works for \<user\> | all machines
2 | \<user\> can `ssh` from \<origin\> to other machines | \<origin\>
3 | `cortx-hare` and `cortx-s3server` RPMs are installed | all machines
4 | `/opt/seagate/cortx/hare/bin` is in \<user\>'s PATH | all machines
5 | \<user\> is a member of `hare` group | all machines
6 | CDF exists and corresponds to the actual cluster configuration | \<origin\>

### Prepare the CDF

To start the cluster for the first time you will need a cluster
description file (CDF).

Make a copy of `/opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml` (single-node setup) or `/opt/seagate/cortx/hare/share/cfgen/examples/ees-cluster.yaml` (dual-node setup).

```sh
cp /opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml ~/CDF.yaml
vi ~/CDF.yaml
```

Edit the copy to match the setup of your cluster.  `host`,
`data_iface`, and `io_disks` fields may need to be modified.

See `cfgen --help-schema` for the description of CDF format.

#### data_iface

* Make sure that `data_iface` value refers to existing network
  interface (it should be present in the output of `ip a` command).

* The network interface specified in `data_iface` must be configured
  for LNet.  If you can see its IP address in the output of
  `sudo lctl list_nids` command, you are all set.  Otherwise,
  configure LNet by executing this code snippet on each node:

  ```sh
  IFACE=eth1  # XXX `data_iface` value from the CDF
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      "options lnet networks=tcp($IFACE) config_on_load=1"
  ```

#### io_disks

* Devices mentioned in `io_disks` section must exist.

* Sometimes it is convenient to use loop devices instead of actual disks:
  ```bash
  sudo mkdir -p /var/motr
  for i in {0..9}; do
      sudo dd if=/dev/zero of=/var/motr/disk$i.img bs=1M seek=9999 count=1
      sudo losetup /dev/loop$i /var/motr/disk$i.img
  done
  ```

### Disable s3auth server

<!-- XXX REVISEME: Provisioner should take care of this. -->
```sh
/opt/seagate/cortx/hare/libexec/s3auth-disable
```

<!------------------------------------------------------------------->
## Hare we go

* Start the cluster.
  ```sh
  hctl bootstrap --mkfs ~/CDF.yaml
  ```

* Run I/O test.

  <!-- XXX
  `m0crate` is a benchmarking tool.  Why would end users want to use
  a benchmarking tool?

  Creating a file
  ```sh
  of=/tmp/128M
  head -c 128M /dev/urandom | tee $of | sha1sum >$of.sha1
  ```
  writing it to Motr object store, and reading back with checksum checked
  should be enough.
  -->

  ```sh
  /opt/seagate/cortx/hare/libexec/m0crate-io-conf >/tmp/m0crate-io.yaml
  dd if=/dev/urandom of=/tmp/128M bs=1M count=128
  sudo m0crate -S /tmp/m0crate-io.yaml
  ```

* Stop the cluster.
  ```sh
  hctl shutdown
  ```

<!------------------------------------------------------------------->
## Reporting problems

To request changes or report a bug, please [log an issue](https://github.com/Seagate/cortx-hare/issues/new) and describe the problem you observe.

When reporting a bug, consider running
```sh
hctl reportbug
```
to collect forensic data.  Run this command on every node of the
cluster and attach generated archive files to the GitHub issue.

<!------------------------------------------------------------------->
## Troubleshooting

### LNet is not configured

* To check, run
  ```sh
  sudo lctl list_nids
  ```
  This command should show network identifiers.

* If it doesn't, try to start LNet manually:
  ```sh
  sudo modprobe lnet
  sudo lctl network up
  ```
  Run `sudo lctl list_nids` again.

* Still no luck?  Perhaps `/etc/modprobe.d/lnet.conf` file is missing
  or corrupted.  Create it with these commands:
  ```sh
  IFACE=eth1  # XXX `data_iface` value from the CDF
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      "options lnet networks=tcp($IFACE) config_on_load=1"
  ```
  Try to start LNet one more time.

### RC Leader cannot be elected

If `hctl bootstrap` cannot complete and keeps printing dots..........
```
2020-01-14 10:57:25: Generating cluster configuration... Ok.
2020-01-14 10:57:26: Starting Consul server agent on this node.......... Ok.
2020-01-14 10:57:34: Importing configuration into the KV Store... Ok.
2020-01-14 10:57:35: Starting Consul agents on remaining cluster nodes... Ok.
2020-01-14 10:57:35: Update Consul agents configs from the KV Store... Ok.
2020-01-14 10:57:36: Install Motr configuration files... Ok.
2020-01-14 10:57:36: Waiting for the RC Leader to get elected..................[goes on forever]
```
try these commands
```sh
hctl shutdown
sudo systemctl reset-failed hare-hax
```
and bootstrap again.

<!------------------------------------------------------------------->
## See also

* [Hare Developer Guide](README_developers.md)
* [Hare RFCs](rfc/README.md)
