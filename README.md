# Hare User Guide

## Welcome

Hare is an experiment in
[Social Architecture](https://www.youtube.com/watch?v=uj-li0LO_2g),
disguised as a software project.

## What Hare does?

The scripts in this repository constitute a middleware layer between [Consul](https://www.consul.io/) and [Motr](https://github.com/Seagate/cortx-motr) services.

Their responsibilities:
1. Configures components of the distributed Motr object store.
2. Makes arrangements to ensure that Motr system remains available even
   if some of its components fail.
3. Provides CLI for starting/stopping Motr system.

Hare implementation uses [Consul](https://www.consul.io) key-value store
and health-checking mechanisms.

<!------------------------------------------------------------------->

## Getting Hare

cortx-hare depends on cortx-motr libraries. Therefore, a correct version of
cotrx-motr must be installed for proper operation. cotrx-motr can be either
installed from packages of build from sources.

Available options:
* Install RPMs from CI build.
  _The easiest way to get Hare + Motr instances up and running._
* Build and install from source code.
  _Works for contribution process._

### Get source code

1. Fork [cortx-hare](https://github.com/Seagate/cortx-hare) repo using Github
   interface.
2. Clone created cortx-hare with submodules.
3. Add Seagate remote:
```
git remote add seagate git@github.com:Seagate/cortx-hare.git
```
Please refer to [README_developers.md](README_developers.md) for instructions
on how to build and install hare from source code.

### Install RPM packages

**WARNING:** This part of instruction is valid only for Seagate engineers so
far. It will be updated once public CI is operational.

Installing `cortx-hare` and `cortx-s3server` packages by running these commands
on every machine in the cluster:
  ```bash
  (set -eu

  if ! rpm -q cortx-hare cortx-s3server; then
      if ! sudo yum install -y cortx-hare cortx-s3server; then
          for x in 'integration/centos-7.7.1908/last_successful' 's3server_uploads'
          do
              repo="cortx-storage.colo.seagate.com/releases/eos/$x"
              sudo yum-config-manager --add-repo="http://$repo"
              sudo tee -a /etc/yum.repos.d/${repo//\//_}.repo <<< 'gpgcheck=0'
          done
          unset repo x

          sudo yum install -y cortx-hare cortx-s3server
      fi
  fi
  )
  ```

## Prerequisites

### Choose a configuration to setup

* Single node with Hare + Motr up and running.
  _Recommended for fast proof of concept check to get familiar with software._
* Cluster setup
  _Intended mode of operation. Several nodes/VM is required. RPM installation
  is recommended._
  **WARNING: will be available once public CI is operational.**

The difference is obviously a number or nodes to configure and the content of
CDF file to be used later in this guide.

### :ballot_box_with_check: Checklist

Before starting the cluster as \<user\> at \<origin\> machine,
ensure that

\# | Check | Where
--- | --- | ---
1 | passwordless `sudo` works for \<user\> | all machines
2 | \<user\> can `ssh` from \<origin\> to other machines | \<origin\>
3 | `cortx-hare` and `cortx-s3server` rpms are installed | all machines
4 | `/opt/seagate/cortx/hare/bin` is in \<user\>'s PATH | all machines
5 | \<user\> is a member of `hare` group | all machines
6 | CDF exists and reflects actual cluster configuration | \<origin\>

* Add `/opt/seagate/cortx/hare/bin` to PATH.
  ```sh
  export PATH="/opt/seagate/cortx/hare/bin:$PATH"
  ```

* Add current user to `hare` group.
  ```sh
  sudo usermod --append --groups hare $USER
  ```
  Log out and log back in to apply changes.

### Prepare a CDF

To start the cluster for the first time you will need a cluster
description file (CDF).

Make a copy of
* `/opt/seagate/cortx/hare/share/cfgen/examples/ees-cluster.yaml` for 2-node
  setup
* `/opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml` for
  single-node setup.

Adapt file to match your cluster configuration: `host`, `data_iface`, and
`io_disks` fields may require modifications.

```sh
cp /opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml ~/CDF.yaml
vi ~/CDF.yaml
```
Make sure interface used for configuration parameter `data_iface` is
configured for lnet.
`sudo lctl list_nids` should show IP address of data_iface.

### Configure lnet driver

Execute these commands on each node (assuming Motr uses `eth0` network
interface):
```bash
sudo tee /etc/modprobe.d/lnet.conf <<< \
    'options lnet networks=tcp(eth0) config_on_load=1'
```

### Create loopback devices

It is possible to make Hare + Motr work without having real block devices.
Loop devices are used in this case.
Create loop devices, if necessary:
```bash
sudo mkdir -p /var/motr
for i in {0..9}; do
    sudo dd if=/dev/zero of=/var/motr/disk$i.img bs=1M seek=9999 count=1
    sudo losetup /dev/loop$i /var/motr/disk$i.img
done
```
Ensure that information in `io_disks` section of CDF file corresponds to
existing devices.

See `cfgen --help-schema` for the description of CDF format.

### Disable s3auth server

<!-- XXX REVISEME: Provisioning should take care of this. -->
```sh
/opt/seagate/cortx/hare/libexec/s3auth-disable
```

<!------------------------------------------------------------------->

## Hare we go

* Start the cluster.
  ```sh
  hctl bootstrap --mkfs ~/CDF.yaml
  ```
  <!-- XXX-UX: s/bootstrap/start/ -->

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

## Troubleshooting

### Ensure that LNet is configured

<!-- XXX When does one have to check this? -->

Run this command:
```sh
sudo lctl list_nids
```

If LNet (Lustre network) is not configured, run
```sh
sudo modprobe lnet
sudo lctl network configure
```

### `lctl list_nids` shows no available interfaces

This is caused by missing `/etc/modprobe.d/lnet.conf` file. Check [Configure lnet driver](#configure-lnet-driver) section.


### hctl reportbug

hctl provides command which gathers all required logs from consul, hax and motr
services.
Those logs can be attached to GitHub issue.
```
hctl reportbug
```

### RC Leader cannot be elected

If `hctl bootstrap` cannot complete and keeps printing dots similarly
to the output below,
```
2020-01-14 10:57:25: Generating cluster configuration... Ok.
2020-01-14 10:57:26: Starting Consul server agent on this node.......... Ok.
2020-01-14 10:57:34: Importing configuration into the KV Store... Ok.
2020-01-14 10:57:35: Starting Consul agents on remaining cluster nodes... Ok.
2020-01-14 10:57:35: Update Consul agents configs from the KV Store... Ok.
2020-01-14 10:57:36: Install Motr configuration files... Ok.
2020-01-14 10:57:36: Waiting for the RC Leader to get elected..................[goes on forever]
```
try the following commands
```sh
hctl shutdown
sudo systemctl reset-failed hare-hax
```
and bootstrap again.

## See also:

* Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md).
* Developers guide: [README_developers.md](README_developers.md).
* Additional documents and API description: [RFCs](rfc/)
