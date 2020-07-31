# Hare Developer Guide

Current document covers building from sources and detailed configuration of Hare service.

Topics described here may require access to Seagate infrastructure.

## 0. Prerequisites

* Repository is cloned along with all submodules. [Link to readme.](README.md#get-source-code)  
  Quick clone from Seagate repo: `git clone --recursive https://github.com/Seagate/cortx-hare.git`

* Python &geq; 3.6 and the corresponding header files.

  To install on CentOS 7, run
  ```sh
  sudo yum install python3 python3-devel
  ```

* Ensure that [Motr](https://github.com/seagate/cortx-motr) is built and its systemd services are installed.  
  _Note: check [cortx-motr](https://github.com/Seagate/cortx-motr/blob/dev/README.md) repo for more details_
  ```sh
  M0_SRC_DIR=/data/mero  # YMMV

  * To install Motr from RPMs:
    ```sh
    sudo yum install cortx-motr cortx-motr-devel
    ```

  * Alternatively, Motr can be compiled and installed from sources:
    ```sh
    git clone --recursive https://github.com/Seagate/cortx-motr.git motr
    M0_SRC_DIR=$PWD/motr

    $M0_SRC_DIR/scripts/m0 make
    sudo $M0_SRC_DIR/scripts/install-motr-service --link
    ```

## 1. Single-node setup

1. Build and install Hare:
   ```sh
   # Run from cortx-hare directory
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
     sudo mkdir -p /var/motr
     for i in {0..9}; do
         sudo dd if=/dev/zero of=/var/motr/disk$i.img bs=1M seek=9999 count=1
         sudo losetup /dev/loop$i /var/motr/disk$i.img
     done
     ```

   * Make sure that `data_iface` value refers to existing network
     interface (it should be present in the output of `ip a` command).

4. Start the cluster.
   ```sh
   hctl bootstrap --mkfs cfgen/examples/singlenode.yaml
   ```

## 2. Test I/O

```sh
utils/m0crate-io-conf >/tmp/m0crate-io.yaml
dd if=/dev/urandom of=/tmp/128M bs=1M count=128
sudo $M0_SRC_DIR/clovis/m0crate/m0crate -S /tmp/m0crate-io.yaml
```

## 3. 3-node SSC VM setup

<!-- XXX Why do we need this section at all?
  -- Is section '4. Multi-node setup' not enough?
  -->

### 3.1. Create VMs

* Login to [Red Hat CloudForms](https://ssc-cloud.colo.seagate.com)
  (aka SSC) using your Seagate GID and password.

* Open
  [Service Catalogs](https://ssc-cloud.colo.seagate.com/catalog/explorer#/).

* Order three "RHEL 7.7 EXT4 (4X50GB Disks)" virtual machines.
  It will take some time <!-- XXX How long? --> for the order to be processed.

* Find host names of your VMs at the bottom of
  [Active Services](https://ssc-cloud.colo.seagate.com/service/explorer#/)
  page.

### 3.2. Install RPMs

Execute following step on all nodes: [README.md#install-rpm-packages]

### 3.3. Create loop devices

Execute `m0setup` on all nodes.

### 3.4. Configure LNet

* Execute these commands on each node (assuming Motr uses `eth0`
  network interface):
  ```bash
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      'options lnet networks=tcp(eth0) config_on_load=1'
  sudo systemctl start lnet
  ```

* Check that LNet works:
  ```sh
  sudo lctl list_nids
  ```
  The output should not be empty.

### 3.5. Prepare SSH keys

Execute these commands on the primary node (node-1):
```sh
ssh-keygen
ssh-copy-id <hostname of node-2>
ssh-copy-id <hostname of node-3>
```

### 3.6. Prepare the CDF

The code snippet below will create the cluster description file (CDF).
You may want to update `OUT`, `NODES`, and `IFACE` values prior to
running the code.  The value of `IFACE` should correspond to the value
used in [step 3.4](#34-configure-lnet).

```bash
(set -eu

# Path to the CDF.
OUT=/tmp/trinodes.yaml

# Host names of the VMs.
NODES=(node-1 node-2 node-3)

# Name of the network interface used for Motr I/O.
IFACE=eth0

node_desc() {
    local name=$1 iface=$2
    cat <<EOF
  - hostname: $name
    data_iface: $iface
    m0_servers:
      - runs_confd: true
        io_disks:
          data: []
      - io_disks:
          data:
            - /dev/loop1
            - /dev/loop2
            - /dev/loop3
            - /dev/loop4
    m0_clients:
        s3: 1
        other: 2
EOF
}

cat <<EOF >$OUT
nodes:
$(node_desc ${NODES[0]} $IFACE)
$(node_desc ${NODES[1]} $IFACE)
$(node_desc ${NODES[2]} $IFACE)
pools:
  - name: the pool
    disks: all
    data_units: 2
    parity_units: 1
EOF
)
```

### 3.7. Disable S3 authentication

```sh
/opt/seagate/eos/hare/libexec/s3auth-disable
```

### 3.8. Bootstrap the cluster

```sh
hctl bootstrap --mkfs /tmp/trinodes.yaml
hctl status
```

### 3.8. Configure S3 client

* We deploy manually, so there is no Cluster IP.  The workaround:
  ```sh
  sudo tee -a /etc/hosts <<< '<IP address of node-1> s3.seagate.com'
  ```

* Configure S3 client: <!-- XXX Which file should this data be put in? -->
  ```
  Access Key: anything
  Secret Key: anything
  Default Region: US
  S3 Endpoint: s3.seagate.com
  DNS-style bucket+hostname:port template for accessing a bucket: %(bucket)s.s3.seagate.com
  Encryption password:
  Path to GPG program: /bin/gpg
  Use HTTPS protocol: False
  HTTP Proxy server name: <IP address of node-1>
  HTTP Proxy server port: 28081
  ```
  `HTTP Proxy server name` field should be set to the IP address of
  the primary node.

  Now execute
  ```sh
  s3cmd --configure
  ```

### 3.8. Test S3 I/O

```sh
(set -eu

fn=lustre-2.12.3-1.src.rpm
s3cmd mb s3://testbkt
s3cmd put /root/$fn s3://testbkt/$fn
s3cmd get s3://testbkt/$fn /tmp/$fn
cmp /root/$fn /tmp/$fn || echo '**ERROR** S3 I/O test failed' >&2
)
```

## 4. Multi-node setup

For multi-node cluster the steps are similar to
[those of single-node](#1-single-node-setup).
Steps 1–2 should be performed on each of the nodes.  The bootstrap
command may be executed on any server node (i.e., on any of the nodes
configured to run confd).

Use `cfgen/examples/ees-cluster.yaml`, which describes a dual-node cluster,
as an example.

## 5. Observe

### 5.1. Consul web UI

To view the [Consul UI](https://learn.hashicorp.com/consul/getting-started/ui#set-up-access-to-the-ui),
open `http://<vm-ip-address>:8500/ui` URL in your browser.

### 5.2. The RC leader

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

### 5.3. Logs

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

## 6. Miscellaneous

* Get an entry point:

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

## 7. Links

- [Halon replacement: a simpler, better HA subsystem for EOS](https://docs.google.com/presentation/d/17Pn61WBbTHpeR4NxGtaDfmmHxgoLW9BnQHRW7WJO0gM/view) (slides)
- [Halon replacement: Consul, design highlights](https://docs.google.com/document/d/1cR-BbxtMjGuZPj8NOc95RyFjqmeFsYf4JJ5Hw_tL1zA/view)
- Bootstrap guide: [README.md](README.md): _how to get source code and run hare + motr instance_.
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md).
