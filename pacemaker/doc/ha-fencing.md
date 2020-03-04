## Set up the environment

***Note***: Before installing, make sure that group ID 189 is not used by any group:

```
getent group 189
```
If the id is assigned, consider removing that group. Otherwise Pacemaker will not be installed properly or there will be nasty side effects while administering it. More details on the issue can be seen [here](https://bugzilla.redhat.com/show_bug.cgi?id=1472369).

### Install pacemaker et al

Run the command at every node within the cluster.
```
# yum install -y pacemaker pcs psmisc policycoreutils-python fence-agents-all
```

### Check if it works

```sh
# pcs stonith list | grep ipmi
fence_ipmilan - Fence agent for IPMI
```

### Setup the cluster

1. Set the password for `hacluster` at every node:
  ```sh
  # echo CHANGEME | passwd --stdin hacluster
  ```
2. Run pcsd service at every node
  ```sh
  # systemctl start pcsd.service
  # systemctl enable pcsd.service
  ```
3. Add the nodes to the cluster:
```sh
  # pcs cluster auth sati30{a,b}-m08 -u hacluster -p CHANGEME --force
  sati30a-m08: Authorized
  sati30b-m08: Authorized
```
4. Start the cluster
  ```sh
  # pcs cluster setup --name mycluster sati30{a,b}-m08 --force
  Destroying cluster on nodes: sati30a-m08, sati30b-m08...
  sati30b-m08: Stopping Cluster (pacemaker)...
  sati30a-m08: Stopping Cluster (pacemaker)...
  sati30b-m08: Successfully destroyed cluster
  sati30a-m08: Successfully destroyed cluster

  Sending 'pacemaker_remote authkey' to 'sati30a-m08', 'sati30b-m08'
  sati30a-m08: successful distribution of the file 'pacemaker_remote authkey'
  sati30b-m08: successful distribution of the file 'pacemaker_remote authkey'
  Sending cluster config files to the nodes...
  sati30a-m08: Succeeded
  sati30b-m08: Succeeded

  Synchronizing pcsd certificates on nodes sati30a-m08, sati30b-m08...
  sati30a-m08: Success
  sati30b-m08: Success
  Restarting pcsd on the nodes in order to reload the certificates...
  sati30a-m08: Success
  sati30b-m08: Success
  ```

## Configure STONITH resources

1. Dump the pacemaker configuration into the xml file:
  ```sh
  # pcs cluster cib stonith.xml
  ```
2. Dishonor loss of quorum (since we have only 2 nodes in the cluster):
  ```sh
  pcs -f stonith.xml property set no-quorum-policy=ignore
  pcs -f stonith.xml property set stonith-enabled=true
  ```
3. Learn the IPMI management IP addresses for each of the machines (below is the example for my machines):
  ```sh
  [root@sati30b-m08 ~]#ipmitool lan print 1 | grep "IP Address  "
  IP Address              : 10.230.163.90

  [root@sati30a-m08 ~]# ipmitool lan print 1 | grep "IP Address  "
  IP Address              : 10.230.161.163
  ```

4. Create the stonith resources in pacemaker (can be run at any of the nodes in cluster)
  ```sh
  pcs -f stonith.xml stonith create sati30b-m08.stonith  \
          fence_ipmilan ipaddr="10.230.163.90" passwd="admin" login="admin" \
          method="onoff" delay=5 pcmk_host_list="sati30b-m08" pcmk_host_check=static-list \
          power_timeout=10 op monitor interval=10s

  pcs -f stonith.xml stonith create sati30a-m08.stonith  \
          fence_ipmilan ipaddr="10.230.161.163" passwd="admin" login="admin" \
          method="onoff" pcmk_host_list="sati30a-m08" pcmk_host_check=static-list \
          power_timeout=10 op monitor interval=10s
  ```
  ***Notes***:
  1. pcmk_host_list option must contain the node (as it is known to Pacemaker) this resource is able to fence.
  2. ipaddr must specify the address of the IPMI management interface.
  3. Command that creates `sati30b-m08.stonith` contains delay parameter which is omitted in the second command. This asymmetry allows to escape fencing loop.

5. Add constraints to stonith resources (to make sure a stonith resource that kills node X will not migrate to node X):
  ```sh
  pcs -f stonith.xml constraint location sati30a-m08.stonith avoids sati30a-m08=INFINITY
  pcs -f stonith.xml constraint location sati30b-m08.stonith avoids sati30b-m08=INFINITY
  ```
6. Finally push the xml configuration to the Pacemaker:
  ```sh
  pcs cluster cib-push ./stonith.xml
  ```


## Check STONITH

Here are some samples how we can double check STONITH and fencing mechanisms are in order.

1. Using stonith_admin tool (shipped together with pacemaker):
  ```sh
  stonith_admin -t 20 --reboot sati30a-m08
  ```
2. Trigger kernel panic at one of the nodes:
  Execute this command at one of the nodes:
  ```sh
  echo c > /proc/sysrq-trigger
  ```

  And then in syslog of another machine we'll notice the messages like these:
  ```
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:   notice: On loss of CCM Quorum: Ignore
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Cluster node sati30b-m08 will be fenced: peer is no longer part of the cluster
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Node sati30b-m08 is unclean
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Action sati30a-m08.stonith_stop_0 on sati30b-m08 is unrunnable (offline)
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Action sati30a-m08.stonith_stop_0 on sati30b-m08 is unrunnable (offline)
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Scheduling Node sati30b-m08 for STONITH
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:   notice:  * Fence (reboot) sati30b-m08 'peer is no longer part of the cluster'
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:   notice:  * Stop       sati30a-m08.stonith     ( sati30b-m08 )   due to node availability
  Dec 16 11:08:35 sati30a-m08 pengine[83309]:  warning: Calculated transition 0 (with warnings), saving inputs in /var/lib/pacemaker/pengine/pe-warn-1.bz2
  Dec 16 11:08:35 sati30a-m08 crmd[83310]:   notice: Requesting fencing (reboot) of node sati30b-m08
  Dec 16 11:08:35 sati30a-m08 stonith-ng[83306]:   notice: Client crmd.83310.2def1613 wants to fence (reboot) 'sati30b-m08' with device '(any)'
  Dec 16 11:08:35 sati30a-m08 stonith-ng[83306]:   notice: Requesting peer fencing (reboot) of sati30b-m08
  Dec 16 11:08:35 sati30a-m08 stonith-ng[83306]:   notice: sati30b-m08.stonith can fence (reboot) sati30b-m08: static-list
  Dec 16 11:08:35 sati30a-m08 stonith-ng[83306]:   notice: sati30b-m08.stonith can fence (reboot) sati30b-m08: static-list
  Dec 16 11:08:36 sati30a-m08 stonith-ng[83306]:   notice: Operation 'reboot' [84476] (call 2 from crmd.83310) for host 'sati30b-m08' with device 'sati30b-m08.stonith' returned: 0 (OK)
  Dec 16 11:08:36 sati30a-m08 stonith-ng[83306]:   notice: Operation reboot of sati30b-m08 by sati30a-m08 for crmd.83310@sati30a-m08.539760a4: OK
```

## [Optional] Leveraging multiple networks in Pacemaker

### Useful links

1. Corosync: Redundant Ring Protocol (https://www.sebastien-han.fr/blog/2012/08/01/corosync-rrp-configuration/)
2. Configuring Network Redundancy for PaceMaker Cluster Communication (https://www.thegeekdiary.com/configuring-network-redundancy-for-pacemaker-cluster-communication/)

### Configuration

***Prerequisites***
1. There are 2 nodes connected via more than one networks.
2. Pacemaker is installed at both machines

***Instruction***

The instruction below assumes we have a cluster of two nodes at `smc22-m10` and `smc21-m10.`

#### Identify the network interfaces at both nodes

```
[root@smc21-m10 ~]# ip a | grep -E '.*inet ' -B 2
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
--
2: eno1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
    link/ether ac:1f:6b:c8:92:c0 brd ff:ff:ff:ff:ff:ff
    inet 10.230.166.138/21 brd 10.230.167.255 scope global noprefixroute dynamic eno1
--
8: bond0: <BROADCAST,MULTICAST,MASTER,UP,LOWER_UP> mtu 9000 qdisc noqueue state UP group default qlen 1000
    link/ether b8:59:9f:d5:5f:5e brd ff:ff:ff:ff:ff:ff
    inet 172.16.0.109/20 brd 172.16.15.255 scope global dynamic bond0
```
> The node smc21-m10 is accessible via the following addresses:
> 1. 10.230.166.138 (network address is 10.230.160.0), this address is resolved by hostname
> 2. 172.16.0.109 (network address is 172.16.0.0)
```
[root@smc22-m10 ~]# ip a | grep -E '.*inet ' -B 2
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
--
2: eno1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
    link/ether ac:1f:6b:c8:92:b0 brd ff:ff:ff:ff:ff:ff
    inet 10.230.166.125/21 brd 10.230.167.255 scope global noprefixroute dynamic eno1
--
8: bond0: <BROADCAST,MULTICAST,MASTER,UP,LOWER_UP> mtu 9000 qdisc noqueue state UP group default qlen 1000
    link/ether 98:03:9b:6b:63:90 brd ff:ff:ff:ff:ff:ff
    inet 172.16.0.108/20 brd 172.16.15.255 scope global dynamic bond0
```

> The node smc22-m10 is accessible via the following addresses:
> 1. 10.230.166.125 (network address is 10.230.160.0), this address is resolved by hostname
> 2. 172.16.0.108 (network address is 172.16.0.0)

#### Add alternative hostnames to both machines that get resolved within `172.16.0.0` network
Add the following lines to `/etc/hosts` file at each machine:
```
10.230.166.138 smc21-m10
172.16.0.109   smc21-m10a
10.230.166.125 smc22-m10
172.16.0.108   smc22-m10a
```

#### Create Pacemaker cluster

```
# pcs cluster setup --name mycluster smc21-m10,smc21-m10a smc22-m10,smc22-m10a --rrpmode=passive --force
# pcs cluster start --all

```

***Note***: The command above (re-)creates cluster named mycluster and specifies the hostnames of the participants (comma separates the alternative hostnames that form another corosync ring).
As a result, `corosync.conf` file looks as follows:


<details>
  <summary>Click to expand</summary>


```
totem {
    version: 2
    cluster_name: mycluster
    secauth: off
    transport: udpu
    rrp_mode: passive
}

nodelist {
    node {
        ring0_addr: smc21-m10
        ring1_addr: smc21-m10a
        nodeid: 1
    }

    node {
        ring0_addr: smc22-m10
        ring1_addr: smc22-m10a
        nodeid: 2
    }
}

quorum {
    provider: corosync_votequorum
    two_node: 1
}

logging {
    to_logfile: yes
    logfile: /var/log/cluster/corosync.log
    to_syslog: yes
}
```


</details>


#### Add simplistic resource

```
# pdsh -w smc21-m10,smc22-m10
> wget https://raw.githubusercontent.com/ClusterLabs/resource-agents/master/heartbeat/anything
> chmod +x  /root/anything

# pcs resource create MyResource ocf:heartbeat:anything binfile="sleep 67"

# pcs status
Cluster name: mycluster
Stack: corosync
Current DC: NONE
Last updated: Tue Jan 28 06:49:00 2020
Last change: Tue Jan 28 05:53:09 2020 by root via cibadmin on smc21-m10

2 nodes configured
1 resource configured

Online: [ smc21-m10 smc22-m10 ]

Full list of resources:

 MyResource     (ocf::heartbeat:anything):      Started smc21-m10

Daemon Status:
  corosync: active/disabled
  pacemaker: active/disabled
  pcsd: active/enabled
```
> Note: if MyResource is in Stopped state, consider either disabling stonith in Pacemaker or setting up fencing resources.

#### Test

***Set eno1 interface down at smc21-m10***

```
[root@smc21-m10 ~]# ifdown eno1
```
> Note: this interface hosts 10.230.160.0 network which corresponds to ring0 in corosync.

***Ensure MyResource is not migrated***

```
# pcs status
Cluster name: mycluster
Stack: corosync
Current DC: smc22-m10 (version 1.1.20-5.el7_7.2-3c4c782f70) - partition with quorum
Last updated: Tue Jan 28 07:12:54 2020
Last change: Tue Jan 28 05:25:16 2020 by root via cibadmin on smc21-m10

2 nodes configured
1 resource configured

Online: [ smc21-m10 smc22-m10 ]

Full list of resources:

 MyResource     (ocf::heartbeat:anything):      Started smc21-m10

Failed Resource Actions:
* MyResource_monitor_10000 on smc21-m10 'unknown error' (1): call=237, status=complete, exitreason='',
    last-rc-change='Tue Jan 28 07:12:31 2020', queued=0ms, exec=0ms
* MyResource_monitor_10000 on smc22-m10 'unknown error' (1): call=225, status=complete, exitreason='',
    last-rc-change='Tue Jan 28 06:47:58 2020', queued=0ms, exec=0ms

Daemon Status:
  corosync: active/disabled
  pacemaker: active/disabled
  pcsd: active/enabled
```

`journalctl -xe` shows that Corosync did notice ring0 is unhealthy but after that we also can see the traces of recovering MyResource - since it is simply `sleep 67`, it exits every 67 seconds and Pacemaker re-launches it again and again. Note that MyResource is kept managed at node smc21-m10 where the ring0 interface is down.


<details>
  <summary>Click to expand</summary>


```
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: Calculated transition 148, saving inputs in /var/lib/pacemaker/pengine/pe-input-163.bz2
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: On loss of CCM Quorum: Ignore
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc21-m10: unknown error
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc22-m10: unknown error
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: Calculated transition 149, saving inputs in /var/lib/pacemaker/pengine/pe-input-164.bz2
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating stop operation MyResource_stop_0 on smc21-m10
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating start operation MyResource_start_0 on smc21-m10
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating monitor operation MyResource_monitor_10000 on smc21-m10
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Transition 149 (Complete=3, Pending=0, Fired=0, Skipped=0, Incomplete=0, Source=/var/lib/pacemaker/pengine/pe-input-164.bz2): Complete
Jan 28 07:12:36 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: State transition S_TRANSITION_ENGINE -> S_IDLE
Jan 28 07:12:53 smc22-m10.mero.colo.seagate.com corosync[209722]:  [TOTEM ] Marking ringid 0 interface 10.230.166.125 FAULTY
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: State transition S_IDLE -> S_POLICY_ENGINE
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: On loss of CCM Quorum: Ignore
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc21-m10: unknown error
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc22-m10: unknown error
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: Calculated transition 150, saving inputs in /var/lib/pacemaker/pengine/pe-input-165.bz2
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: On loss of CCM Quorum: Ignore
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc21-m10: unknown error
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc22-m10: unknown error
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: Calculated transition 151, saving inputs in /var/lib/pacemaker/pengine/pe-input-166.bz2
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating stop operation MyResource_stop_0 on smc21-m10
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating start operation MyResource_start_0 on smc21-m10
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Initiating monitor operation MyResource_monitor_10000 on smc21-m10
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: Transition 151 (Complete=3, Pending=0, Fired=0, Skipped=0, Incomplete=0, Source=/var/lib/pacemaker/pengine/pe-input-166.bz2): Complete
Jan 28 07:13:46 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: State transition S_TRANSITION_ENGINE -> S_IDLE
Jan 28 07:14:56 smc22-m10.mero.colo.seagate.com crmd[209742]:   notice: State transition S_IDLE -> S_POLICY_ENGINE
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: On loss of CCM Quorum: Ignore
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc21-m10: unknown error
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc22-m10: unknown error
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: Calculated transition 152, saving inputs in /var/lib/pacemaker/pengine/pe-input-167.bz2
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice: On loss of CCM Quorum: Ignore
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc21-m10: unknown error
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:  warning: Processing failed monitor of MyResource on smc22-m10: unknown error
Jan 28 07:14:57 smc22-m10.mero.colo.seagate.com pengine[209741]:   notice:  * Recover    MyResource     ( smc21-m10 )
```


</details>
