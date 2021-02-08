[![Codacy Badge](https://app.codacy.com/project/badge/Grade/0642a6f7d92542e39f2dd68139cd5586)](https://www.codacy.com/gh/Seagate/cortx-hare/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=Seagate/cortx-hare&amp;utm_campaign=Badge_Grade) [![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/Seagate/cortx-hare/blob/main/LICENSE) [![Slack](https://img.shields.io/badge/chat-on%20Slack-blue")](https://join.slack.com/t/cortxcommunity/shared_invite/zt-femhm3zm-yiCs5V9NBxh89a_709FFXQ?) [![YouTube](https://img.shields.io/badge/Video-YouTube-red)](https://cortx.link/videos)

# Hare User Guide

## What Hare does?

1. Configures [Motr](https://github.com/seagate/cortx-motr) object store.
2. Starts/stops Motr services.
3. Notifies Motr of service and device faults.

Hare implementation uses [Consul](https://www.consul.io) key-value store
and health-checking mechanisms.

<!------------------------------------------------------------------->
## Installation

<!-- XXX-RESTOREME
### RPM package

* Install `yum-config-manager` to manage your repositories.
  ```sh
  sudo yum -y install yum-utils
  ```

* Add the official Seagate repository.
  ```sh
  sudo yum-config-manager --add-repo XXX-TBD
  ```

* Add the official Hashicorp Consul repository.
  ```sh
  sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  ```

* Install `cortx-hare`.
  ```sh
  sudo yum -y install cortx-hare
  ```
-->

### Building from source

* Download Hare.
  ```sh
  git clone https://github.com/Seagate/cortx-hare.git hare
  cd hare
  ```

* Install Python (&ge; 3.6), libraries and header files needed to
  compile Python extensions.
  ```sh
  sudo yum -y install python3 python3-devel
  ```

* Install Consul.
  ```sh
  sudo yum -y install yum-utils
  sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  sudo yum -y install consul-1.7.8
  ```

* Create new file:

  ```vi /etc/yum.repos.d/cortx_iso.repo```
* Paste following code into file:
  ``` 
  [cortx_iso]
  baseurl=file:///var/artifacts/0//cortx_iso
  gpgcheck=0
  name=Repository cortx_iso
  enabled=1
  ```
* Create new file:
  ```vi /etc/yum.repos.d/C7.8.2003.repo```
* Paste into file:
  ```
  # C7.8.2003
  [C7.8.2003-base]
  name=CentOS-7.8.2003 - Base
  baseurl=http://linuxsoft.cern.ch/centos-vault/7.8.2003/os/$basearch/
  gpgcheck=1
  gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
  enabled=1

  [C7.8.2003-updates]
  name=CentOS-7.8.2003 - Updates
  baseurl=http://linuxsoft.cern.ch/centos-vault/7.8.2003/updates/$basearch/
  gpgcheck=1
  gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
  enabled=0

  [C7.8.2003-extras]
  name=CentOS-7.8.2003 - Extras
  baseurl=http://linuxsoft.cern.ch/centos-vault/7.8.2003/extras/$basearch/
  gpgcheck=1
  gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
  enabled=1

  [C7.8.2003-centosplus]
  name=CentOS-7.8.2003 - CentOSPlus
  baseurl=http://linuxsoft.cern.ch/centos-vault/7.8.2003/centosplus/$basearch/
  gpgcheck=1
  gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
  enabled=1

  [C7.8.2003-fasttrack]
  name=CentOS-7.8.2003 - Fasttrack
  baseurl=http://linuxsoft.cern.ch/centos-vault/7.8.2003/fasttrack/$basearch/
  gpgcheck=1
  gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
  enabled=1
  ```
* Create new file:
  ```sh 
  vi /etc/yum.repos.d/cortx_iso.repo 
  ```

* Paste into file:

  ```sh
  [cortx_3rdparty]
  baseurl=file:///var/artifacts/0/3rd_party
  gpgcheck=0
  name=Repositoryi 3rdparty
  enabled=1
  ```

* Make sure that "lustre-whamcloud-2.12.5" is not listed:

    ```sh
      yum list lustre-client-devel kmod-lustre-client 
    ```

    * If "lustre-whamcloud-2.12.5" is listed:

      ```sh
        vi /etc/yum.repos.d/lustre-whamcloud.repo
      ```

   * and change from: 

      ```sh
      [lustre-whamcloud-2.12.5]
      baseurl = https://downloads.whamcloud.com/public/lustre/lustre-2.12.5/el7/client/
      enabled = 1
      gpgcheck = 0
      name = Whamcloud - Lustre 2.12.5
      ```
   * to:

      ```sh
      [lustre-whamcloud-2.12.5]
      baseurl = https://downloads.whamcloud.com/public/lustre/lustre-2.12.5/el7/client/
      enabled = 0
      gpgcheck = 0
      name = Whamcloud - Lustre 2.12.5
      ```

* Install Motr.

  * .. from RPMs
    ```sh
    sudo yum -y install cortx-motr cortx-motr-devel
    ```

  * .. or from sources
    ```sh
    git clone --recursive https://github.com/Seagate/cortx-motr.git motr
    cd motr

    scripts/m0 make
    sudo scripts/install-motr-service --link

    export M0_SRC_DIR=$PWD
    cd -
    ```

* Build and install Hare.
  ```sh
  make
  sudo make devinstall
  ```

* Add current user to `hare` group.
  ```sh
  sudo usermod --append --groups hare $USER
  ```
  Log out and log back in.


### Build and install `hare` rpm from source.

* Install Motr.

  * .. from RPMS
    ```sh
    sudo yum -y install cortx-motr cortx-motr-devel
    ```

  * .. or from sources
    ```sh
    git clone --recursive https://github.com/Seagate/cortx-motr.git motr
    cd motr

    scripts/m0 make rpms
    sudo rpm -ivh ~/rpmbuild/RPMS/x86_64/cortx-motr-*.rpm
    ```

* Build `hare` rpm.

  Download hare source as mentioned above.
  ```sh
  cd hare

  make rpm
  sudo rpm -ivh ~/rpmbuild/RPMS/x86_64/cortx-hare-*.rpm
  ```


<!------------------------------------------------------------------->
## Quick start

:ballot_box_with_check: **Checklist**

Before starting the cluster as \<user\> at \<origin\> machine,
ensure that

\# | Check | Where
--- | --- | ---
1 | passwordless `sudo` works for \<user\> | all machines
2 | \<user\> can `ssh` from \<origin\> to other machines | \<origin\>
3 | `cortx-hare` and `cortx-s3server` RPMs are installed | all machines
4 | `/opt/seagate/cortx/hare/bin` is in \<user\>'s PATH | all machines
5 | \<user\> is a member of `hare` group | all machines
6 | CDF exists and corresponds to the actual cluster configuration | \<origin\>

### Prepare the CDF

If you are starting the cluster for the first time, you will need a
_cluster description file_ (CDF).

See `cfgen --help-schema` for the description of CDF format.

You can make a copy of
`/opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml`
(single-node setup) or
`/opt/seagate/cortx/hare/share/cfgen/examples/ldr1-cluster.yaml`
(dual-node setup) and edit it as necessary.

```sh
cp /opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml ~/CDF.yaml
vi ~/CDF.yaml
```

You will probably need to modify `host`, `data_iface`, and `io_disks` values.

#### data_iface

* Make sure that `data_iface` value refers to existing network
  interface (it should be present in the output of `ip a` command).

* This network interface must be configured for LNet.  If you can see
  its IP address in the output of `sudo lctl list_nids` command, you
  are all set.  Otherwise, configure LNet by executing this code
  snippet on each node:
  ```bash
  IFACE=eth1  # XXX `data_iface` value from the CDF
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      "options lnet networks=tcp($IFACE) config_on_load=1"
  ```

#### io_disks

* Devices specified in `io_disks` section must exist.

* Sometimes it is convenient to use loop devices instead of actual disks:
  ```bash
  sudo mkdir -p /var/motr
  for i in {0..9}; do
      sudo dd if=/dev/zero of=/var/motr/disk$i.img bs=1M seek=9999 count=1
      sudo losetup /dev/loop$i /var/motr/disk$i.img
  done
  ```

### Hare we go

* Start the cluster.
  ```sh
  hctl bootstrap --mkfs ~/CDF.yaml
  ```

* Run I/O test.

  <!-- XXX
  `m0crate` is a benchmarking tool.  Why would end users want to use
  a benchmarking tool?

  Creating a file
  ```sh
  of=/tmp/128M
  head -c 128M /dev/urandom | tee $of | sha1sum >$of.sha1
  ```
  writing it to Motr object store, and reading back with checksum checked
  should be enough.
  -->

  ```sh
  /opt/seagate/cortx/hare/libexec/m0crate-io-conf >/tmp/m0crate-io.yaml
  dd if=/dev/urandom of=/tmp/128M bs=1M count=128
  sudo m0crate -S /tmp/m0crate-io.yaml
  ```
  Please note that m0crate will run as shown above when it will be
  available in default system PATH which will be the case when
  setup is created using RPMs. If its created by building Motr
  source code, then m0crate utility can be run using full path from
  the motr source directory (say MOTR_SRC).
  ./MOTR_SRC/motr/m0crate/m0crate

* Stop the cluster.
  ```sh
  hctl shutdown
  ```

<!------------------------------------------------------------------->
## Reporting problems

To request changes or report a bug, please
[log an issue](https://github.com/Seagate/cortx-hare/issues/new)
and describe the problem you are facing.

When reporting a bug, consider running
```sh
hctl reportbug
```
to collect forensic data.  Run this command on every node of the
cluster and attach generated files to the GitHub issue.

<!------------------------------------------------------------------->
## Troubleshooting

### LNet is not configured

* To check, run
  ```sh
  sudo lctl list_nids
  ```
  This command should show network identifiers.

* If it doesn't, try to start LNet manually:
  ```sh
  sudo modprobe lnet
  sudo lctl network up
  ```
  Run `sudo lctl list_nids` again.

* Still no luck?  Perhaps `/etc/modprobe.d/lnet.conf` file is missing
  or corrupted.  Create it with these commands:
  ```sh
  IFACE=eth1  # XXX `data_iface` value from the CDF
  sudo tee /etc/modprobe.d/lnet.conf <<< \
      "options lnet networks=tcp($IFACE) config_on_load=1"
  ```
  Try to start LNet one more time.

### RC Leader cannot be elected

If `hctl bootstrap` cannot complete and keeps printing dots..........
```
2020-01-14 10:57:25: Generating cluster configuration... Ok.
2020-01-14 10:57:26: Starting Consul server agent on this node.......... Ok.
2020-01-14 10:57:34: Importing configuration into the KV Store... Ok.
2020-01-14 10:57:35: Starting Consul agents on remaining cluster nodes... Ok.
2020-01-14 10:57:35: Update Consul agents configs from the KV Store... Ok.
2020-01-14 10:57:36: Install Motr configuration files... Ok.
2020-01-14 10:57:36: Waiting for the RC Leader to get elected..................[goes on forever]
```
try these commands
```sh
hctl shutdown
sudo systemctl reset-failed hare-hax
```
and bootstrap again.

<!------------------------------------------------------------------->
## See also

* [Hare RFCs](rfc/README.md)
* [Hare wiki](https://github.com/Seagate/cortx-hare/wiki)
