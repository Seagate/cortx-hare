---
domain: github.com
shortname: 4/KV
name: Consul KV Schema
status: draft
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
  - Mandar Sawant <mandar.sawant@seagate.com>
  - Rajanikant Chirmade <rajanikant.chirmade@seagate.com>
---

## Consul KV Schema

Key | Value | Description
--- | --- | ---
`bq/<epoch>` | (conf object fid, HA state) | `bq/*` items are collectively referred to as the BQ (Broadcast Queue).  The items - HA state updates - are produced by the RC (Recovery Coordinator) script.
`epoch` | current epoch | Atomically incremented counter, which is used to generate unique ordered identifiers for EQ and BQ entries.  Natural number.
`eq/<epoch>` | event | `eq/*` items are collectively referred to as the EQ (Event Queue).  Events are consumed and dequeued by the RC script.
`last_fidk` | last generated fid key | Atomically incremented counter that is used to generate fids.
`leader` | node name | This key is used for RC leader election.  Created with [`consul lock`](https://www.consul.io/docs/commands/lock.html) command.
`m0conf/nodes/<name>/processes/<process_fidk>/endpoint` | endpoint address | Endpoint address of the Motr process (Consul service) with fid key `<process_fidk>`.  Example: `192.168.180.162@tcp:12345:44:101`.
`m0conf/nodes/<name>/processes/<process_fidk>/meta_data` | path to meta-data disk | `m0mkfs` uses this value to create meta-data pool.
`m0conf/nodes/<name>/processes/<process_fidk>/services/<svc_type>` | Fid key | Fid key of the Motr service, specified by its type, parent process, and node.
`m0conf/nodes/<node_fid>` | `{ "name": "<node name>", "state": "<HA state>" }` |
`m0conf/nodes/<node_fid>/processes/<process_fid>` | `{ "name": "<process name>", "state": "<HA state>" }` |
`m0conf/nodes/<node_fid>/processes/<process_fid>/services/<svc_fid>` | `{ "name": "<service name>", "state": "<HA state>" }` |
`m0conf/nodes/<node_fid>/processes/<process_fid>/services/<svc_fid>/sdevs/<sdev_fid>` | `{ "path": "<sdev path>", "state": "<HA state>" }` |
`m0conf/pools/<pool_fid>` | pool name | Name of the pool as specified in the CDF.  Example: `tier1-nvme`.
`m0conf/profiles/<profile_fid>` | `{ "name": "<profile_name>", "pools": [ "<pool_name>" ] }` | "pools" - names of the _SNS_ pools associated with this profile.  `<profile_name>` and `<pool_name>`s are specified in the CDF.
`m0conf/sites/<site_fid>` | `{ "state": "<HA state>" }` | [HA state](#ha-state) of this site.
`m0conf/sites/<site_fid>/racks/<rack_fid>` | `{ "state": "<HA state>" }` | [HA state](#ha-state) of this rack.
`m0conf/sites/<site_fid>/racks/<rack_fid>/encls/<encl_fid>` | `{ "state": "<HA state>" }` | [HA state](#ha-state) of this enclosure.
`m0conf/sites/<site_fid>/racks/<rack_fid>/encls/<encl_fid>/ctrls/<ctrl_fid>` | `{ "node": "<node_fid>", "state": "<HA state>" }` | Fid of the corresponding node and [HA state](#ha-state) of this controller.
`m0conf/sites/<site_fid>/racks/<rack_fid>/encls/<encl_fid>/ctrls/<ctrl_fid>/drives/<drive_fid>` | `{ "dev": "<sdev_fid>", "state": "<HA state>" }` | Fid of the corresponding storage device and [HA state](#ha-state) of this drive.
`processes/<fid>` | `{ "state": "<HA state>" }` | The items are created and updated by `hax` processes.  Supported values of \<HA state\>: `M0_CONF_HA_PROCESS_STARTING`, `M0_CONF_HA_PROCESS_STARTED`, `M0_CONF_HA_PROCESS_STOPPING`, `M0_CONF_HA_PROCESS_STOPPED`.
`sspl.SYSTEM_INFORMATION.log_level` | | This key is used by SSPL.
`stats/filesystem` | JSON object | See ['stats/filesystem' value](#statsfilesystem-value) below.
`timeout` | YYYYmmddHHMM.SS | This value is used by the RC timeout mechanism.

**Note:** Fid keys are non-negative integers, base 10.

<!--
  XXX TODO: s/processes/m0-servers/

  Word "process" is ambiguous, we should be more specific.
  We are dealing with a subset of m0_conf_process objects.
  The items correspond to m0d processes --- Motr servers.

  'm0-processes' is also slightly more greppable.
-->
<!--
  XXX Problem: How will `bootstrap` be able to tell whether given fid
  corresponds to m0mkfs or m0d?

  Solution: We could use optional `"is-m0mkfs": true` field...

  Right now we don't know for sure if this will actually be a problem.
  The [specification of `bootstrap` script](rfc/6/README.md) should
  cover this topic.
-->
<!--
  XXX 'sspl.SYSTEM_INFORMATION.log_level' does not conform to the naming
  convention used for other entries.  It would be nice to rename that key
  to 'sspl/log-level'.
  See https://jts.seagate.com/browse/EOS-6473?focusedCommentId=1818633&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-1818633
-->

### HA state

See [`enum m0_ha_obj_state`](https://github.com/Seagate/cortx-motr/blob/dev/ha/note.h#L119) in Motr code, `ha/note.h`.

### 'stats/filesystem' value

Example:

```json
{
  "stats": {
    "fs_free_seg": 71468251167696,
    "fs_total_seg": 10995118312064,
    "fs_free_disk": 429084411691008,
    "fs_avail_disk": 429084411691008,
    "fs_total_disk": 429084412739584,
    "fs_svc_total": 4,
    "fs_svc_replied": 4
  },
  "timestamp": 1588596031.468349,
  "date": "2020-05-04T12:40:31.468349"
}
```

Field | Description
--- | ---
`fs_free_seg`    | free bytes in BE segments
`fs_total_seg`   | total bytes in BE segments
`fs_free_disk`   | free bytes on drives
`fs_avail_disk`  | available bytes on drives
`fs_total_disk`  | total bytes on drives
`fs_svc_total`   | total number of IOS, MDS, and CAS services
`fs_svc_replied` | how many of them have replied

Corresponding Motr structure: [`struct m0_fs_stats`][spiel/m0_fs_stats]

[spiel/m0_fs_stats]: https://github.com/Seagate/cortx-motr/blob/dev/spiel/spiel.h#L1268
