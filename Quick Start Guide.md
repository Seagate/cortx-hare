# Quick Start Guide

This document provides detailed information on the installation of Hare component.

## Prerequisites

* Repository must be cloned along with all submodules using the below mentioned commands. 

    `git clone --recursive https://github.com/Seagate/cortx-hare.git`
    
    `cd hare`
  
* Python &geq; 3.6 and the corresponding header files. Run the below mentioned command to install the same.

   `sudo yum install python3 python3-devel`

* CentOS 7 must be available.

* The `cortx-motr` and `cortx-motr-devel` RPMs must be installed. Refer [Motr Quick Start Guide](https://github.com/Seagate/cortx-motr/blob/dev/doc/Quick-Start-Guide.rst).

* Alternatively, Motr can be compiled and installed from the source.
  ```sh
  git clone --recursive https://github.com/Seagate/cortx-motr.git motr
  cd motr

  scripts/m0 make
  sudo scripts/install-motr-service --link

  M0_SRC_DIR=$PWD
  cd -
  ```
  See [Motr Quick Start Guide](https://github.com/Seagate/cortx-motr/blob/dev/doc/Quick-Start-Guide.rst#building-the-source-code) for more details.
      
* Build and install Hare by running the below mentioned commands from the cortx-hare directory. 
   ```sh
   
   make
   
   sudo make devinstall

* Run the below mentioned command to add current user to `hare` group. Then, log out and log in.
   
   `sudo usermod --append --groups hare $USER`
   
## 3-node SSC VM setup

<!-- XXX Why do we need this section at all?
  -- Is section '4. Multi-node setup' not enough?
  -->

### Create VMs

* Login to [Red Hat CloudForms](https://ssc-cloud.colo.seagate.com)
  (aka SSC) using your Seagate GID and password.

* Open
  [Service Catalogs](https://ssc-cloud.colo.seagate.com/catalog/explorer#/).

* Order three "RHEL 7.7 EXT4 (4X50GB Disks)" virtual machines.
  It will take some time <!-- XXX How long? --> for the order to be processed.

* Find host names of your VMs at the bottom of
  [Active Services](https://ssc-cloud.colo.seagate.com/service/explorer#/)
  page.

### Install RPMs

Run the following code snippet on every node (VM).
 ```bash
  (set -eu

  if ! rpm -q cortx-hare cortx-s3server; then
      if ! sudo yum install -y cortx-hare cortx-s3server; then
          for x in integration/centos-7.7.1908/last_successful s3server_uploads
          do
              repo="cortx-storage.colo.seagate.com/releases/eos/$x"
              sudo yum-config-manager --add-repo="http://$repo"
              sudo tee -a /etc/yum.repos.d/${repo//\//_}.repo <<< gpgcheck=0
          done
          unset repo x

          sudo yum install -y cortx-hare cortx-s3server
      fi
  fi
  )
  ```

### Loop Devices

Execute `m0setup` on all nodes to setup loop devices.

### Configure LNet

Perform the procedure mentioned below to configure LNet.

1. Run the below mentioned commands on each node (assuming Motr uses `eth0`
  network interface).
  ```bash
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      'options lnet networks=tcp(eth0) config_on_load=1'
  sudo systemctl start lnet
  ```

2. Run the below mentioned command to ensure that LNet works.
  
     `sudo lctl list_nids`
  
      The output should not be empty.

### Prepare SSH keys

Run the below mentioned commands on the primary node (node-1) to generate SSH Keys.

* `ssh-keygen`

* `ssh-copy-id <hostname of node-2>`

* `ssh-copy-id <hostname of node-3>`

### Prepare the CDF

The code snippet below will create the cluster description file (CDF).
You may want to update `OUT`, `NODES`, and `IFACE` values prior to
running the code.  The value of `IFACE` should correspond to the one
from [Configure LNet](#configure-lnet) section.

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

### Disable S3 Authentication

Run the below mentioned command to disable S3 authentication.

* `/opt/seagate/eos/hare/libexec/s3auth-disable`


### Bootstrap the cluster

Run the below mentioned commands to bootstrap the cluster.

* `hctl bootstrap --mkfs /tmp/trinodes.yaml`

* `hctl status`

### Configure S3 client

1. Deployment happens manually, so there is no Cluster IP. Hence, run the following command.

  
   `sudo tee -a /etc/hosts <<< '<IP address of node-1> s3.seagate.com'`
 

2. Configure the S3 client based on the data below.<!-- XXX Which file should this data be put in? -->

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
  The `HTTP Proxy server name` field should be set to the IP address of the primary node.
  
3. Run the following command.
 
    `s3cmd --configure`
 

### Test S3 I/O

The testing of S3 I/O is mentioned below.

```sh
(set -eu

fn=lustre-2.12.3-1.src.rpm
s3cmd mb s3://testbkt
s3cmd put /root/$fn s3://testbkt/$fn
s3cmd get s3://testbkt/$fn /tmp/$fn
cmp /root/$fn /tmp/$fn || echo '**ERROR** S3 I/O test failed' >&2
)
```

## Observe

### Consul web UI

To view the [Consul UI](https://learn.hashicorp.com/consul/getting-started/ui#set-up-access-to-the-ui),
open the below mentioned URL in your browser.

* `http://<vm-ip-address>:8500/ui`

### The RC leader

The RC leader election related information can be viewed below.

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

***Note:*** The presence of the `Session` line indicates that the leader has been elected.


### Logs

* Run the below mentioned command to generate the RC leader election log.

    `tail -f /var/log/hare/consul-elect-rc-leader.log`

* Run the below mentioned command to generate the RC log.

    `tail -f /var/log/hare/consul-proto-rc.log`

* Run the below mentioned command to generate the system log.

    `journalctl --since <HH:MM> # bootstrap time`

## Miscellaneous

* The code block below showcases the command and output with regards to getting an entry point.

  ```sh
  $ ./get-entrypoint
  principal-RM: node0
  confds:
    - node: node0
      fid: 0x7200000000000001:0x0002
      address: 192.168.180.162@tcp:12345:44:101
  ```

* The code block below showcases the command and output with regards to adding a timeout and monitoring it. 

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

## Troubleshooting

### Unknown tag: package package is not installed

An example of the error with `make rpm` command is displayed below.
```
--> Preparing rpmbuild environment
‘cortx-hare-1.0.0.tar.gz’ -> ‘/home/vagrant/rpmbuild/SOURCES/cortx-hare-1.0.0.tar.gz’
‘hare.spec’ -> ‘/home/vagrant/rpmbuild/SPECS/hare.spec’
make[1]: Leaving directory `/tmp/cortx-hare'
make[1]: Entering directory `/tmp/cortx-hare'
--> Building rpm packages
error: line 33: Unknown tag: package package is not installed
make[1]: *** [__rpm] Error 1
make[1]: Leaving directory `/tmp/cortx-hare'
make: *** [rpm] Error 2
```
This is caused by missing submodules. It happens when repository is cloned without `--recursive` flag.


Solution: Clone using the `git submodule update --init --recursive` command.

## References

- [Halon replacement: a simpler, better HA subsystem for EOS](https://docs.google.com/presentation/d/17Pn61WBbTHpeR4NxGtaDfmmHxgoLW9BnQHRW7WJO0gM/view) (slides)
- [Halon replacement: Consul, design highlights](https://docs.google.com/document/d/1cR-BbxtMjGuZPj8NOc95RyFjqmeFsYf4JJ5Hw_tL1zA/view)
- Bootstrap guide: [README.md](README.md): _how to get source code and run hare + motr instance_.
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md).
