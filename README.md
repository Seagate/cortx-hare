# Hare - Halon replacement

The scripts in this repository constitute a middleware layer between [Consul](https://www.consul.io/) and [Mero](http://gitlab.mero.colo.seagate.com/mero/mero) services.  Their responsibilities:

- provide initial configuration for a Mero cluster;
- mediate communications between Mero services and Consul agents.

## Installation

[Download Consul](https://www.consul.io/downloads.html).  Copy `consul` executable to a $PATH directory (e.g., `/usr/local/bin/`) on each node of the cluster.

### Single node

1. Prepare the node:
   ```sh
   cd
   git clone ssh://git@gitlab.mero.colo.seagate.com:6022/mero/hare.git
   sudo mkdir -p /opt/seagate
   sudo ln -s ~/hare /opt/seagate/consul
   touch /tmp/confd  # "Mero confd service is alive and well" indicator
   ```

2. Start Consul server agent:
   ```sh
   consul agent -bind='{{GetPrivateIP}}' -server -config-dir=~/hare \
       -data-dir=/tmp/consul -bootstrap-expect=1 \
       -client='127.0.0.1 {{GetPrivateIP}}' -ui &
   ```

3. Initialise Consul KV store:
   ```sh
   cd hare
   ./kv-init
   ```

4. Generate and assign Mero process fids to the "services", mentioned in `consul-srv-conf.json`:
   ```sh
   ./gen-service-ids
   ```

### Multiple nodes

1. Prepare each of the cluster nodes; see step 1 of the [Single node](#single-node) section.

2. Start Consul agent (server or client) on each of the nodes.  Use [`-retry-join`](https://www.consul.io/docs/agent/options.html#_retry_join) option so that it joins already running Consul server(s).
   ```sh
   consul agent -bind='{{GetPrivateIP}}' -server -config-dir=~/hare \
       -data-dir=/tmp/consul -retry-join=192.168.180.1
   ```
   **Note:** If you plan to test RC leader election, there should be at least 3 Consul servers in the cluster.

3. Generate and assign Mero process fids:
   ```sh
   ./gen-service-ids
   ```

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
  $ pgrep -a consul
  9100 consul agent -bind={{GetPrivateIP}} -server -config-dir=/home/ant/hare -data-dir=/tmp/consul/ -bootstrap-expect=1 -client=127.0.0.1 {{GetPrivateIP}} -ui
  9656 consul watch -type=keyprefix -prefix eq/ /home/ant/hare/proto-rc
  ```

  The `consul watch [...] -prefix eq/` line indicates that the leader has been elected.  If there is no such line, try `consul reload`.

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
