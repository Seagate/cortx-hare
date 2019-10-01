# Hare - Halon replacement

The scripts in this repository constitute a middleware layer between [Consul](https://www.consul.io/) and [Mero](http://gitlab.mero.colo.seagate.com/mero/mero) services.  Their responsibilities:

- generate initial configuration of Mero cluster;
- mediate communications between Mero services and Consul agents.

## Dependencies

* Python &geq; 3.6
* [Consul](https://www.consul.io/downloads.html)
* [Dhall](https://github.com/dhall-lang/dhall-lang/wiki/Getting-started%3A-Generate-JSON-or-YAML#linux)

## Installation

* Copy `consul` executable to a `$PATH` directory (e.g., `/usr/local/bin/`) on each node of the cluster.
* Install Python dependencies:
  ```sh
  pip3 install -r hax/requirements.txt
  ```
* Ensure that Mero sources are built.
  ```sh
  $M0_SRC_DIR/scripts/m0 make
  ```
  <!-- XXX TODO: Hare should be able to work with Mero installed from rpm. -->

### Single-node setup

1. Prepare the node:
   ```sh
   cd
   git clone ssh://git@gitlab.mero.colo.seagate.com:6022/mero/hare.git
   cd hare
   ./install
   ```
2. Edit `./cfgen/_misc/singlenode.yaml` file
  1. Ensure that `data_iface` value corresponds to a real network interface (see output of `ifconfig` command)

3. Start Hare cluster:
   ```sh
   ./bootstrap ./cfgen/_misc/singlenode.yaml
   ```

### Multi-node setup

For multi-node cluster the steps are the same as for single-node. Installation and node preparation steps should be done on each node. The cluster descripion file preparation and bootstrap command run can be done on any server node (the one which is configured to run confd).

## Observe

* RC leader election log:
  ```sh
  tail -f /tmp/consul-elect-rc-leader.log
  ```

* RC log:
  ```sh
  tail -f /tmp/consul-proto-rc.log
  ```

* Check if the RC leader has been elected:

```sh
$ consul kv get -detailed leader
CreateIndex      6
Flags            0
Key              leader
LockIndex        1
ModifyIndex      25
Session          d5f3f364-6f79-48cd-b452-913321b2c743
Value            sage75
```

***Note:*** The presence of the `Session` ID indicates that the leader has been elected.

### Consul web UI

To view the [Consul UI](https://learn.hashicorp.com/consul/getting-started/ui#set-up-access-to-the-ui), open `http://<vm-ip-address>:8500/ui` URL in your browser.

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

  ```sh
  $ tail -f /tmp/consul-proto-rc.log &
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

  The timeout resets automatically (for demo purposes), so you will see it in the log file every other minute.

## Roadmap

1. EES release (due at the end of 2019) — Halon is replaced in Mero software stack with Consul & ‘hare’ scripts.  Failover is performed by [Pacemaker](https://clusterlabs.org/pacemaker/).

2. EOS release — Consul takes over Pacemaker's responsibilities.

See also [plan.org](./plan.org).

## Links

- [Halon replacement: a simpler, better HA subsystem for EOS](https://docs.google.com/presentation/d/17Pn61WBbTHpeR4NxGtaDfmmHxgoLW9BnQHRW7WJO0gM/view) (slides)
- [Halon replacement: Consul, design highlights](https://docs.google.com/document/d/1cR-BbxtMjGuZPj8NOc95RyFjqmeFsYf4JJ5Hw_tL1zA/view)
