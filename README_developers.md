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

## Test I/O

```sh
utils/m0crate-io-conf >/tmp/m0crate-io.yaml
dd if=/dev/urandom of=/tmp/128M bs=1M count=128
sudo $M0_SRC_DIR/clovis/m0crate/m0crate -S /tmp/m0crate-io.yaml
```

## 3-node VM setup

0. Create three nodes from service catalogs (RHEL 7.7 EXT4 (4x50GB Disks) on https://ssc-cloud.colo.seagate.com .

1. Add yum repositories for Cortx and dependant software components on all nodes.

   ```sh
   sudo yum-config-manager \
   --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/s3server_uploads \
   --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/lustre/custom/tcp \
   --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/integration/centos-7.7.1908/last_successful \
   --add-repo=http://ssc-satellite1.colo.seagate.com/pulp/repos/EOS/Library/custom/CentOS-7/CentOS-7-OS
   ```

2. Install MOTR, S3 Server, Hare on all nodes.

   ```sh
   yum install -y --nogpgcheck eos-core eos-core-devel eos-s3server eos-hare
   ```

3. Create virtual devices on all nodes.

   ```sh
   m0setup
   ```

4. Configure Lnet on all nodes.
   - edit /etc/modprobe.d/lnet.conf file with network interface used by MOTR endpoints.

   ```sh
   echo "options lnet networks=tcp(eth0) config_on_load=1" > /etc/modprobe.d/lnet.conf
   systemctl start lnet
   lctl list_nids
   ```

5. Copy ssh keys to other nodes from node-1.
   ```sh
   ssh-keygen
   ssh-copy-id  <hostname of node-2>
   ssh-copy-id  <hostname of node-3>
   ```

6. Edit cluster defination file with layout 2 + 1 on node-1.
   Add $HOME/threenodes.yaml

   ```
   nodes:
     - hostname: <hostname of node-1>
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
     - hostname: <hostname of node-2>
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
     - hostname: <hostname of node-3>
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
   - Make sure value of `data_iface` is same as used for lnet @ step (4).
7. Bootstrap the cluster.

   ```sh
   hctl bootstrap --mkfs $HOME/threenodes.yaml
   hctl status
   ```

8. Disable S3 authentication on node-1 since S3 Auth server not provisioned
   yet with manual setup.
   ```sh
   hctl shutdown
   /opt/seagate/eos/hare/libexec/s3auth-disable
   hctl bootstrap --mkfs $HOME/threenodes.yaml
   ```

9. Do S3 IO on client node.

   - Install S3 client node (can get one from ssc cloud).

   ```sh
   sudo yum-config-manager --add-repo=http://ci-storage.mero.colo.seagate.com/releases/eos/s3server_uploads
   yum install -y --nogpgcheck s3cmd
   ```

   - Append /etc/hosts to point s3.seagate.com to node-1
     (No Cluster IP on mannual setup).

   ```sh
   echo "<node-1 IP address> s3.seagate.com" > /etc/hosts
   ```
   - Configure S3 client, use following configuration values.

     ```
     Access Key: <any string>
     Secret Key: <any string>
     Default Region: US
     S3 Endpoint: s3.seagate.com
     DNS-style bucket+hostname:port template for accessing a bucket: %(bucket)s.s3.seagate.com
     Encryption password:
     Path to GPG program: /bin/gpg
     Use HTTPS protocol: False
     HTTP Proxy server name: <IP address of node-1>
     HTTP Proxy server port: 28081
     ```
   - Make sure use IP address and port of S3 server instance on node-1 since
     in manual setup no HA Proxy installed.

   ```sh
   s3cmd --configure
   ```

   - Test S3 IO.
   ```sh
   s3cmd mb s3://testbkt
   s3cmd put /root/lustre-2.12.3-1.src.rpm  s3://testbkt/lustre-2.12.3-1.src.rpm
   s3cmd get s3://testbkt/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
   diff /root/lustre-2.12.3-1.src.rpm /tmp/lustre-2.12.3-1.src.rpm
   ```

## Multi-node setup

For multi-node cluster the steps are similar to those of single-node.
Steps 1–2 should be performed on each of the nodes.  The bootstrap
command may be executed on any server node (i.e., on any of the nodes
configured to run confd).

Use `cfgen/examples/ees-cluster.yaml`, which describes a dual-node cluster,
as an example.

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
