# Hare - Halon replacement

The scripts in this repository form a middleware layer between [Consul](https://www.consul.io/) and [Mero](http://gitlab.mero.colo.seagate.com/mero/mero) services.  Their responsibilities:

- provide initial configuration for a Mero cluster;
- mediate communications between Mero services and Consul agents.

## Roadmap

0. Write the fortnight (2-weeks) prototype.  See [plan.org](./plan.org) for details.

1. EES release (due at the end of 2019) — Halon is replaced in Mero software stack with Consul & ‘hare’ scripts.  Failover is performed by [Pacemaker](https://clusterlabs.org/pacemaker/).

2. EOS release — Consul takes over Pacemaker's responsibilities.

## Singlenode setup

Download Consul binary 1st to your Linux vm and put it some directory from the PATH
(like to /usr/local/bin/).

0. Prepare the node:
   ```
   git clone ssh://git@gitlab.mero.colo.seagate.com:6022/mero/hare.git
   sudo mkdir -p /opt/seagate
   sudo ln -s $HOME/hare /opt/seagate/consul
   touch /tmp/confd # simulate Mero confd service good health
   ```
1. Start Consul server agent:
   ```
   consul agent -bind='{{GetPrivateIP}}' -server -config-dir=$HOME/hare -data-dir=/tmp/consul -bootstrap-expect=1 -client='127.0.0.1 {{GetPrivateIP}}' -ui &
   ```
3. Init KV Store:
   ```
   cd hare
   ./kv-init
   ```
4. Update Mero services FIDs
   ```
   ./update-service-fid
   ```
After this your singlenode setup should be ready. To see the RC leader election log in real-time:
```
tail -f /tmp/consul-elect-rc-leader.log &
```
To see the RC log:
```
tail -f /tmp/consul-proto-rc.log &
```
To check if the RC leader is elected:
```
$ pgrep -a consul
9100 consul agent -bind={{GetPrivateIP}} -server -config-dir=/home/ant/hare -data-dir=/tmp/consul/ -bootstrap-expect=1 -client=127.0.0.1 {{GetPrivateIP}} -ui
9656 consul watch -type=keyprefix -prefix eq/ /home/ant/hare/proto-rc
```
The presence of `consul watch...proto-rc` process indicates that it was.

That's basically it. Your setup is ready for experiments and developing. For example, you can get entry point:
```
$ ./get-entrypoint 
principal-RM: node0
confds:
  - node: node0
    fid: 0x7200000000000001:0x0002
    address: 192.168.180.162@tcp:12345:44:101
```

Or add some timeout and monitor it via the log file:
```
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
...
```
The timeout is automatically re-set (just for the demo purposes) so you will see it in the log file every other minute.

You can check your setup in browser also by http://your-vm-IP-address:8500.

## Multi-nodes setup
Multinodes setup is easy. On each node the step (0) (Prepare the node) should be
performed 1st. Then you should start the Consul agent in server or client mode
(there should be at least 3 server nodes if you want to test RC Leader election)
and join it to already started agent with the -retry-join option like this:
```
consul agent -bind='{{GetPrivateIP}}' -server -config-dir=$HOME/hare -data-dir=/tmp/consul -retry-join=192.168.180.1
```
Then perform step 4 (Update Mero services FIDs) from the above.

That's it.

## Links

- [Halon replacement: a simpler, better HA subsystem for EOS](https://docs.google.com/presentation/d/17Pn61WBbTHpeR4NxGtaDfmmHxgoLW9BnQHRW7WJO0gM/view) (slides)
- [Halon replacement: Consul, design highlights](https://docs.google.com/document/d/1cR-BbxtMjGuZPj8NOc95RyFjqmeFsYf4JJ5Hw_tL1zA/view)
