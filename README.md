# Hare

## Welcome

Hare is an experiment in
[Social Architecture](https://www.youtube.com/watch?v=uj-li0LO_2g),
disguised as a software project.

## What Hare does?

1. Configures components of the distributed Mero object store.
2. Makes arrangements to ensure that Mero system remains available even
   if some of its components fail.
3. Provides CLI for starting/stopping Mero system.

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
3 | `lustre-client` rpm is installed | all machines
4 | `hare` and `s3server` rpms are installed | all machines
5 | `/opt/seagate/hare/bin` is in \<user\>'s PATH | all machines
6 | \<user\> is a member of `hare` group | all machines
7 | CDF exists and reflects actual cluster configuration | \<origin\>

### LNet

Mero object store uses Lustre networking (LNet).  Run these commands
on every machine of the cluster to ensure that LNet is installed:

```bash
(set -eu

if ! rpm -q lustre-client --quiet lustre-client; then
    if ! sudo yum install -y lustre-client; then
        repo=downloads.whamcloud.com/public/lustre/lustre-2.10.4/el7/client
        sudo yum-config-manager --add-repo=https://$repo
        sudo tee -a /etc/yum.repos.d/${repo//\//_}.repo <<< gpgcheck=0
        unset repo

        sudo yum install -y lustre-client
    fi
fi

# `lnetctl import /etc/lnet.conf` will fail unless /etc/lnet.conf
# exists and is a valid YAML document.  YAML document cannot be empty;
# document separator ('---') is the shortest valid YAML document.
if [[ ! -s /etc/lnet.conf ]]; then
    sudo tee /etc/lnet.conf <<<'---' >/dev/null
fi
)
```

### Install rpm packages

* Install `hare` and `s3server` packages by running these commands on
  every machine of the cluster:
  ```bash
  (set -eu

  if ! rpm -q hare s3server; then
      if ! sudo yum install -y hare s3server; then
          repo="ci-storage.mero.colo.seagate.com/releases/eos/BLATEST"
          yum-config-manager --add-repo="http://$repo"
          sudo tee -a /etc/yum.repos.d/${repo//\//_}.repo <<< 'gpgcheck=0'
          unset repo

          sudo yum install -y hare s3server
      fi
  fi
  )
  ```

* Add `/opt/seagate/hare/bin` to PATH.
  ```sh
  export PATH="/opt/seagate/hare/bin:$PATH"
  ```

* Add current user to `hare` group.
  ```sh
  sudo usermod --append --groups hare $USER
  ```
  Log out and log back in.

### Prepare a CDF

To start the cluster for the first time you will need a cluster
description file (CDF).

Make a copy of
`/opt/seagate/hare/share/cfgen/examples/ees-cluster.yaml` (or
`singlenode.yaml` in case of single-node setup) and adapt it to match
your cluster.  `host`, `data_iface`, and `io_disks` fields may require
modifications.

```sh
cp /opt/seagate/hare/share/cfgen/examples/ees-cluster.yaml ~/CDF.yaml
vi ~/CDF.yaml
```

See `cfgen --help-schema` for the description of CDF format.

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
  writing it to Mero object store, and reading back with checksum checked
  should be enough.
  -->

  ```sh
  /opt/seagate/hare/libexec/hare/m0crate-io-conf >/tmp/m0crate-io.yaml
  dd if=/dev/urandom of=/tmp/128M bs=1M count=128
  sudo m0crate -S /tmp/m0crate-io.yaml
  ```

* Stop the cluster.
  ```sh
  hctl shutdown
  ```

## Contributing

This project uses
[PC3 (Pedantic Code Construction Contract)](rfc/9/README.md)
process for contributions.

To build from sources, see the README_developers.md file.
