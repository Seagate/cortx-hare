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

1. Build and install Hare:
   ```sh
   git clone --recursive http://gitlab.mero.colo.seagate.com/mero/hare.git
   cd hare
   make
   sudo make devinstall
   ```

2. Add current user to `hare` group.
   ```sh
   sudo usermod --append --groups hare $USER
   ```
   Log out and log back in.

3. Edit `cfgen/examples/singlenode.yaml` file.

   * Ensure that the disks enumerated in the `io_disks` list exist.
     Create loop devices, if necessary:
     ```bash
     sudo mkdir -p /var/mero
     for i in {0..9}; do
         sudo dd if=/dev/zero of=/var/mero/disk$i.img bs=1M seek=9999 count=1
         sudo losetup /dev/loop$i /var/mero/disk$i.img
     done
     ```

   * Make sure that `data_iface` value refers to existing network
     interface (it should be present in the output of `ip a` command).

4. Start the cluster.
   ```sh
   hctl bootstrap --mkfs cfgen/examples/singlenode.yaml
   ```

## Multi-node setup

For multi-node cluster the steps are similar to those of single-node.
Steps 1–2 should be performed on each of the nodes.  The bootstrap
command may be executed on any server node (i.e., on any of the nodes
configured to run confd).

Use `cfgen/examples/ees-cluster.yaml`, which describes a dual-node cluster,
as an example.

## 3 Node setup

0. Create three nodes fron service catalogs (RHEL 7.7 EXT4 (4x50GB Disks) on https://ssc-cloud.colo.seagate.com/

1. Add S3 server dependancies repo   (On all nodes)

   ```sh
   sudo yum-config-manager --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/s3server_uploads
   ```

2. Add repo for luster               (On all nodes)

   ```sh
   sudo yum-config-manager --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/lustre/custom/tcp
   ```

3. Add repor for CORTEX              (On all nodes)

   ```sh
   sudo yum-config-manager --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/integration/centos-7.7.1908/last_successful
   ```

4. Add repo for pacemaker (It will be removed after pacemaker related things moved to cortex-ha)       (On all nodes)
   - add /etc/yum.repos.d/base.repo with following contents

 ```
[base]
gpgcheck=0
enabled=1
baseurl=http://ssc-satellite1.colo.seagate.com/pulp/repos/EOS/Library/custom/CentOS-7/CentOS-7-OS/
name=base
```

5. Install MOTR, S3 Server, Hare      (On all nodes)

   ```sh
   yum install -y --nogpgcheck eos-core eos-core-devel eos-s3server eos-hare
   ```

6. Set hostname as node-name          (On all nodes)

   ```sh
   hostname > /var/lib/hare/node-name
   ```

7. Create virtual devices             (On all nodes)

   ```sh
   m0setup
   ```

8. Configure Lnet                     (On all nodes)
   - edit /etc/modprobe.d/lnet.conf file with netowork interface used by MOTR endpoints'

   ```
   options lnet networks=tcp(eth0) config_on_load=1
   ```
   - Check lnet nids
 
   ```sh
   systemctl start lnet
   lctl list_nids #check nids
   ```

9. Add key to nodes   (On node-1)
   ```sh
   ssh-keygen
   ssh-copy-id  <node-2>
   ssh-copy-id  <node-2>
   ```

10. Edit cluster defination with layout 2 + 1   (On 1st node)
   Add $HOME/threenodes.yaml
   ```
nodes:
  - hostname: node-1  (hostname)
    data_iface: eth0
    m0_servers:
      - runs_confd: true
        io_disks: []
      - io_disks:
          - /dev/loop1
          - /dev/loop2
          - /dev/loop3
          - /dev/loop4
    m0_clients:
        s3: 1
        other: 2
  - hostname: node-2  (hostname)
    data_iface: eth0
    m0_servers:
      - runs_confd: true
        io_disks: []
      - io_disks:
          - /dev/loop1
          - /dev/loop2
          - /dev/loop3
          - /dev/loop4
    m0_clients:
        s3: 1
        other: 2
  - hostname: node-2  (hostname)
    data_iface: eth0
    m0_servers:
      - runs_confd: true
        io_disks: []
      - io_disks:
          - /dev/loop1
          - /dev/loop2
          - /dev/loop3
          - /dev/loop4
    m0_clients:
        s3: 1
        other: 2
pools:
  - name: the pool
    disks: all
    data_units: 2
    parity_units: 1
    # allowed_failures: { site: 0, rack: 0, encl: 0, ctrl: 0, disk: 0 }
```
11. Bootstrap cluster

   ```sh
   hctl bootstrap --mkfs $HOME/threenodes.yaml
   ```
```
[root@ssc-vm-0442 520422]# hctl bootstrap --mkfs threenode.yaml
2020-06-12 07:19:30: Generating cluster configuration... OK
2020-06-12 07:19:33: Starting Consul server agent on this node.............. OK
2020-06-12 07:19:44: Importing configuration into the KV store... OK
2020-06-12 07:19:45: Starting Consul agents on other cluster nodes.... OK
2020-06-12 07:19:46: Updating Consul agents configs from the KV store... OK
2020-06-12 07:19:47: Installing Mero configuration files... OK
2020-06-12 07:19:48: Waiting for the RC Leader to get elected... OK
2020-06-12 07:19:48: Starting Mero (phase1, mkfs)... OK
2020-06-12 07:19:53: Starting Mero (phase1, m0d)... OK
2020-06-12 07:19:56: Starting Mero (phase2, mkfs)... OK
2020-06-12 07:20:01: Starting Mero (phase2, m0d)... OK
2020-06-12 07:20:04: Starting S3 servers (phase3)... OK
2020-06-12 07:20:06: Checking health of services... OK
[root@ssc-vm-0442 520422]# hctl status
Profile: 0x7000000000000001:0x7b
Data pools:
    0x6f00000000000001:0x7c
Services:
    ssc-vm-0444.colo.seagate.com  (RC)
    [started]  hax        0x7200000000000001:0x56  10.230.245.167@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x59  10.230.245.167@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0x5c  10.230.245.167@tcp:12345:2:2
    [started]  s3server   0x7200000000000001:0x6c  10.230.245.167@tcp:12345:3:1
    [started]  s3server   0x7200000000000001:0x6f  10.230.245.167@tcp:12345:3:2
    [started]  s3server   0x7200000000000001:0x72  10.230.245.167@tcp:12345:3:3
    [unknown]  m0_client  0x7200000000000001:0x75  10.230.245.167@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x78  10.230.245.167@tcp:12345:4:2
    ssc-vm-0442.colo.seagate.com
    [started]  hax        0x7200000000000001:0x6   10.230.250.241@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x9   10.230.250.241@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0xc   10.230.250.241@tcp:12345:2:2
    [started]  s3server   0x7200000000000001:0x1c  10.230.250.241@tcp:12345:3:1
    [started]  s3server   0x7200000000000001:0x1f  10.230.250.241@tcp:12345:3:2
    [started]  s3server   0x7200000000000001:0x22  10.230.250.241@tcp:12345:3:3
    [unknown]  m0_client  0x7200000000000001:0x25  10.230.250.241@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x28  10.230.250.241@tcp:12345:4:2
    ssc-vm-0443.colo.seagate.com
    [started]  hax        0x7200000000000001:0x2e  10.230.250.160@tcp:12345:1:1
    [started]  confd      0x7200000000000001:0x31  10.230.250.160@tcp:12345:2:1
    [started]  ioservice  0x7200000000000001:0x34  10.230.250.160@tcp:12345:2:2
    [started]  s3server   0x7200000000000001:0x44  10.230.250.160@tcp:12345:3:1
    [started]  s3server   0x7200000000000001:0x47  10.230.250.160@tcp:12345:3:2
    [started]  s3server   0x7200000000000001:0x4a  10.230.250.160@tcp:12345:3:3
    [unknown]  m0_client  0x7200000000000001:0x4d  10.230.250.160@tcp:12345:4:1
    [unknown]  m0_client  0x7200000000000001:0x50  10.230.250.160@tcp:12345:4:2
[root@ssc-vm-0442 520422]#
```

12. S3 IO - S3 auth server not provisioned yet  (On node-1)
```sh
   hctl shutdown
   /opt/seagate/eos/hare/libexec/s3auth-disable
   hctl bootstrap --mkfs $HOME/threenodes.yaml
   ```


12. Do S3 IO (on client node)

   - Edit /etc/hosts to point s3.seagate.com to node-1   (No Cluster IP on mannual setup)

```
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6

10.230.250.241 s3.seagate.com iam.seagate.com
```
   - Test S3 IO
   ```sh
   s3cmd mb s3://testbkt
   s3cmd put /root/lustre-2.12.3-1.src.rpm  s3://testbkt/lustre-2.12.3-1.src.rpm
   s3cmd get s3://testbkt/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
   diff /root/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
   ```
   ```
[root@ssc-vm-0023 520422]# s3cmd mb s3://testbkt
Bucket 's3://testbkt/' created
[root@ssc-vm-0023 520422]# s3cmd ls
2020-06-17 10:24  s3://testbkt
[root@ssc-vm-0023 520422]#
[root@ssc-vm-0023 520422]# s3cmd put /root/lustre-2.12.3-1.src.rpm  s3://testbkt/lustre-2.12.3-1.src.rpm
upload: '/root/lustre-2.12.3-1.src.rpm' -> 's3://testbkt/lustre-2.12.3-1.src.rpm'  [1 of 1]
 14848544 of 14848544   100% in    0s    48.45 MB/s  done
[root@ssc-vm-0023 520422]# s3cmd get s3://testbkt/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
download: 's3://testbkt/lustre-2.12.3-1.src.rpm' -> '/tmp/lustre-2.12.3-1.src.rpm'  [1 of 1]
 14848544 of 14848544   100% in    1s    13.99 MB/s  done
[root@ssc-vm-0023 520422]# diff /root/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
[root@ssc-vm-0023 520422]#
```

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
  tail -f /var/log/hare/consul-elect-rc-leader.log
  ```

* RC log:
  ```sh
  tail -f /var/log/hare/consul-proto-rc.log
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
  $ tail -f /var/log/hare/consul-proto-rc.log &
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
