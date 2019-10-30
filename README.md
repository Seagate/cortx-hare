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
4 | `mero` and `hare` rpms are installed | all machines
5 | `/opt/seagate/hare/bin` is in \<user\>'s PATH | all machines
6 | CDF exists and corresponds to cluster setup | \<origin\>

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

### Install Mero and Hare

* Download `mero` and `hare`
  [rpm packages](http://ci-storage.mero.colo.seagate.com/releases/master/BCURRENT/).

* Install them on every machine of the cluster.

* Add `/opt/seagate/hare/bin` to PATH.
  ```sh
  export PATH="/opt/seagate/hare/bin:$PATH"
  ```

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

* Start the cluster

  ```sh
  hctl bootstrap --mkfs ~/CDF.yaml
  ```
  <!-- XXX-UX: s/bootstrap/start/ -->

* Run I/O test

  **XXX TODO:** Simplify.
  <!-- XXX
  `m0crate` is a benchmarking tool.  Why would end users want to use
  benchmarking tool?

  Creating a file
  ```sh
  of=/tmp/128M
  head -c 128M /dev/urandom | tee $of | sha1sum >$of.sha1
  ```
  writing it to Mero object store, and reading back with checksum checked
  should be enough.
  -->

  ```sh
  cat <<'EOF' >/tmp/test-io.yaml
  CrateConfig_Sections: [MERO_CONFIG, WORKLOAD_SPEC]

  MERO_CONFIG:
    MERO_LOCAL_ADDR: 192.168.122.122@tcp:12345:33:302
    MERO_HA_ADDR:    192.168.122.122@tcp:12345:34:101
    CLOVIS_PROF: <0x7000000000000001:0x4d>  # profile
    LAYOUT_ID: 9                      # defines the UNIT_SIZE (9: 1MB)
    IS_OOSTORE: 1                     # is oostore-mode?
    IS_READ_VERIFY: 0                 # enable read-verify?
    CLOVIS_TM_RECV_QUEUE_MIN_LEN: 16  # minimum length of the receive queue
    CLOVIS_MAX_RPC_MSG_SIZE: 65536    # maximum rpc message size
    CLOVIS_PROCESS_FID: <0x7200000000000001:0x28>
    CLOVIS_IDX_SERVICE_ID: 1

  LOG_LEVEL: 4  # err(0), warn(1), info(2), trace(3), debug(4)

  WORKLOAD_SPEC:              # workload specification section
    WORKLOAD:                 # first workload
      WORKLOAD_TYPE: 1        # index(0), IO(1)
      WORKLOAD_SEED: tstamp   # SEED to the random number generator
      OPCODE: 3               # operation(s) to test: 2-WRITE, 3-WRITE+READ
      CLOVIS_IOSIZE: 10m      # total size of IO to perform per object
      BLOCK_SIZE: 2m          # in N+K conf set to (N * UNIT_SIZE) for max perf
      BLOCKS_PER_OP: 1        # number of blocks per Clovis operation
      MAX_NR_OPS: 1           # max concurrent operations per thread
      NR_OBJS: 10             # number of objects to create by each thread
      NR_THREADS: 4           # number of threads to run in this workload
      RAND_IO: 1              # random (1) or sequential (0) IO?
      MODE: 1                 # synchronous=0, asynchronous=1
      THREAD_OPS: 0           # all threads write to the same object?
      NR_ROUNDS: 1            # number of times this workload is run
      EXEC_TIME: unlimited    # execution time (secs or "unlimited")
      SOURCE_FILE: /tmp/128M  # source data file
  EOF

  /opt/seagate/hare/libexec/hare/update-m0crate-io-test-conf /tmp/test-io.yaml
  dd if=/dev/urandom of=/tmp/128M bs=1M count=128
  sudo m0crate -S /tmp/test-io.yaml
  ```

* Stop the cluster

  ```sh
  hctl shutdown
  ```
  <!-- XXX-UX: s/shutdown/stop/ -->

## Contributing

This project uses
[PC3 (Pedantic Code Construction Contract)](rfc/9/README.md)
process for contributions.

To build from sources, see the README_developers.md file.
