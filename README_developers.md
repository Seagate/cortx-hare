# Hare - Halon replacement

The scripts in this repository constitute a middleware layer between [Consul](https://www.consul.io/) and [Mero](http://gitlab.mero.colo.seagate.com/mero/mero) services.  Their responsibilities:

- generate initial configuration of Mero cluster;
- mediate communications between Mero services and Consul agents.

## Prerequisites

* Python &geq; 3.6 and the corresponding header files.

  To install them on CentOS 7.6, run
  ```sh
  sudo yum install python3 python3-devel
  ```

* Ensure that Mero is built and its systemd services are installed.
  ```sh
  M0_SRC_DIR=/data/mero  # YMMV

  $M0_SRC_DIR/scripts/m0 make
  sudo $M0_SRC_DIR/scripts/install-mero-service --link
  ```
  <!-- XXX TODO: Hare should be able to work with Mero installed from rpm. -->

## Single-node setup

1. Prepare the node:
   ```sh
   git clone --recursive ssh://git@gitlab.mero.colo.seagate.com:6022/mero/hare.git
   cd hare
   make
   sudo make devinstall
   ```

2. Edit `cfgen/examples/singlenode.yaml` file.

   * Ensure that the disks referred to by `io_disks.path_glob` pattern
     exist.  Create loop devices, if necessary:
     ```bash
     sudo mkdir -p /var/mero
     for i in {0..9}; do
         sudo dd if=/dev/zero of=/var/mero/disk$i.img bs=1M seek=9999 count=1
         sudo losetup /dev/loop$i /var/mero/disk$i.img
     done
     ```

   * If `data_iface` field is specified, make sure that it refers to
     an existing network interface (it should be present in the output
     of `ip a` command).

3. Start the cluster:
   ```sh
   hctl bootstrap --mkfs cfgen/examples/singlenode.yaml
   ```

## Multi-node setup

For multi-node cluster the steps are similar to those of single-node.
Steps 1 and 2 should be done for each of the nodes.  The bootstrap
command may be executed on any server node (i.e., on any of the nodes
configured to run confd).

Use `cfgen/examples/ees-cluster.yaml` (which describes a two-node cluster)
as an example.

## Test I/O

```sh
utils/m0crate-io-conf >/tmp/m0crate-io.yaml
dd if=/dev/urandom of=/tmp/128M bs=1M count=128
sudo $M0_SRC_DIR/clovis/m0crate/m0crate -S /tmp/m0crate-io.yaml
```

## Observe

### Consul web UI

To view the [Consul UI](https://learn.hashicorp.com/consul/getting-started/ui#set-up-access-to-the-ui),
open `http://<vm-ip-address>:8500/ui` URL in your browser.

### The RC leader

```
$ consul kv get -detailed leader
CreateIndex      6
Flags            0
Key              leader
LockIndex        1
ModifyIndex      25
Session          d5f3f364-6f79-48cd-b452-913321b2c743
Value            sage75
```

***Note:*** The presence of the `Session` line indicates that the leader
has been elected.

### Logs

* RC leader election log:
  ```sh
  tail -f /var/lib/hare/consul-elect-rc-leader.log
  ```

* RC log:
  ```sh
  tail -f /var/lib/hare/consul-proto-rc.log
  ```

* System log:
  ```sh
  journalctl --since <HH:MM> # bootstrap time
  ```

## Miscellanea

* Get an entrypoint:

  ```sh
  $ ./get-entrypoint
  principal-RM: node0
  confds:
    - node: node0
      fid: 0x7200000000000001:0x0002
      address: 192.168.180.162@tcp:12345:44:101
  ```

* Add a timeout and monitor it via the log:

  ```
  $ tail -f /var/lib/hare/consul-proto-rc.log &
  [2] 10457
  $
  $ consul kv put timeout/201907221208.00 tmo1
  Success! Data written to: timeout/201907221208.00
  $
  $ consul kv put eq/0 wake_RC
  Success! Data written to: eq/0
  $ 2019-07-22 12:09:33 134: Process eq/0 wake_RC...
  2019-07-22 12:09:33 Success! Deleted key: eq/0
  2019-07-22 12:09:34 Success! Data written to: eq/000000002
  2019-07-22 12:09:34 Success! Deleted key: timeout/201907221208.00
  2019-07-22 12:09:34 137: Process eq/000000002 tmo1...
  2019-07-22 12:09:34 Success! Data written to: timeout/201907221210.34
  2019-07-22 12:09:34 Success! Deleted key: eq/000000002
  [...]
  ```

  The timeout resets automatically (for demo purposes), so you will
  see it in the log file every other minute.

## Roadmap

1. EES release (due at the end of 2019) — Halon is replaced in Mero software stack with Consul & ‘hare’ scripts.  Failover is performed by [Pacemaker](https://clusterlabs.org/pacemaker/).

2. EOS release — Consul takes over Pacemaker's responsibilities.

See also [plan.org](./plan.org).

## Links

- [Halon replacement: a simpler, better HA subsystem for EOS](https://docs.google.com/presentation/d/17Pn61WBbTHpeR4NxGtaDfmmHxgoLW9BnQHRW7WJO0gM/view) (slides)
- [Halon replacement: Consul, design highlights](https://docs.google.com/document/d/1cR-BbxtMjGuZPj8NOc95RyFjqmeFsYf4JJ5Hw_tL1zA/view)
