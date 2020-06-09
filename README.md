# Hare

## Welcome

Hare is an experiment in
[Social Architecture](https://www.youtube.com/watch?v=uj-li0LO_2g),
disguised as a software project.

## What Hare does?

1. Configures components of the distributed Motr object store.
2. Makes arrangements to ensure that Motr system remains available even
   if some of its components fail.
3. Provides CLI for starting/stopping Motr system.

Hare implementation leverages the key-value store and health-checking
mechanisms of [Consul](https://www.consul.io) service networking
solution.

## Prerequisites

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

### Install rpm packages

* Install `cortx-hare` and `cortx-s3server` packages by running these commands
  on every machine of the cluster:
  ```bash
  (set -eu

  if ! rpm -q cortx-hare cortx-s3server; then
      if ! sudo yum install -y cortx-hare cortx-s3server; then
          for x in 'integration/centos-7.7.1908/last_successful' 's3server_uploads'
          do
              repo="ci-storage.mero.colo.seagate.com/releases/eos/$x"
              sudo yum-config-manager --add-repo="http://$repo"
              sudo tee -a /etc/yum.repos.d/${repo//\//_}.repo <<< 'gpgcheck=0'
          done
          unset repo x

          sudo yum install -y cortx-hare cortx-s3server
      fi
  fi
  )
  ```

* Add `/opt/seagate/cortx/hare/bin` to PATH.
  ```sh
  export PATH="/opt/seagate/cortx/hare/bin:$PATH"
  ```

* Add current user to `hare` group.
  ```sh
  sudo usermod --append --groups hare $USER
  ```
  Log out and log back in.

### Check motr-kernel service

Motr processes require Motr kernel module to be inserted.
Make sure Motr kernel service is running:
```sh
[[ $(systemctl is-active motr-kernel) == active ]] ||
    sudo systemctl start motr-kernel
```

### Check LNet network ids

Check if LNet network ids are configured:
```sh
sudo lctl list_nids
```

If not configured, run
```sh
sudo modprobe lnet
sudo lctl network configure
```

### Prepare a CDF

To start the cluster for the first time you will need a cluster
description file (CDF).

Make a copy of
`/opt/seagate/cortx/hare/share/cfgen/examples/ees-cluster.yaml` (or
`singlenode.yaml` in case of single-node setup) and adapt it to match
your cluster.  `host`, `data_iface`, and `io_disks` fields may require
modifications.

```sh
cp /opt/seagate/cortx/hare/share/cfgen/examples/ees-cluster.yaml ~/CDF.yaml
vi ~/CDF.yaml
```
Make sure interface used for configuration parameter `data_iface` is
configured for lnet.
`sudo lctl list_nids` should show IP address of data_iface.

See `cfgen --help-schema` for the description of CDF format.

### Disable s3auth server

<!-- XXX REVISEME: Provisioning should take care of this. -->
```sh
/opt/seagate/cortx/hare/libexec/s3auth-disable
```

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

## Troubleshooting

### RC Leader cannot be elected

If `hctl bootstrap` cannot complete and keeps printing dots similarly to the output below,
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

## Contributing

This project uses
[PC3 (Pedantic Code Construction Contract)](rfc/9/README.md)
process for contributions.

To build from sources, see the README_developers.md file.
