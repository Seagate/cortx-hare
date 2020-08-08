<!--
  Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  For any questions about this software or licensing,
  please email opensource@seagate.com or cortx-questions@seagate.com.
-->

---
domain: gitlab.mero.colo.seagate.com
shortname: 4/KV
name: Consul KV Schema
status: draft
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
  - Mandar Sawant <mandar.sawant@seagate.com>
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
`m0conf/nodes/<name>/processes/<process_fidk>/services/<svc_type>` | Fid key | Fid key of the Motr service, specified by its type, parent process, and node.
`m0conf/profiles/<profile_fidk>` | `[ <pool_fidk> ]` | Array of fid keys of the SNS pools associated with this profile.
`processes/<fid>` | `{ "state": "<HA state>" }` | The items are created and updated by `hax` processes.  Supported values of \<HA state\>: `M0_CONF_HA_PROCESS_STARTING`, `M0_CONF_HA_PROCESS_STARTED`, `M0_CONF_HA_PROCESS_STOPPING`, `M0_CONF_HA_PROCESS_STOPPED`.
`profile` | fid | Profile fid in string format.  Example: `"0x7000000000000001:0x4"`.
`profile/pools` | fids | Space-separated list of fids of SNS pools.
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
  XXX Human-readable pool names (e.g., "tier1-nvme", "tier2-ssd", "tier3-hdd")
  proved to be quite useful in multi-pool setups.  If pool information is
  ever needed, consider the following format of pool entries:

  `m0conf/pools/<pool_fidk>` | `{ "name": <pool name>, ...N K failvec... }`
-->
<!--
  XXX 'sspl.SYSTEM_INFORMATION.log_level' does not conform to the naming
  convention used for other entries.  It would be nice to rename that key
  to 'sspl/log-level'.
  See https://jts.seagate.com/browse/EOS-6473?focusedCommentId=1818633&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-1818633
-->

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

[spiel/m0_fs_stats]: http://gitlab.mero.colo.seagate.com/mero/mero/blob/3c6e1148ff5fb18b81236700396bd7881ad61c18/spiel/spiel.h#L1251
