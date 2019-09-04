---
domain: gitlab.mero.colo.seagate.com
shortname: 4/KV
name: Consul KV Schema
status: raw
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
`leader` | node name | This key is used for RC leader election.  Created with [`consul lock`](https://www.consul.io/docs/commands/lock.html) command.
`last_fidk` | last genarated FID key | Atomically incremented counter that is used to generate fids.  Natural number.
`node/<name>/service/<service_type>/<fid_key>` | `""` | The data contained in the key is being used during update of Consul configuration files.  Supported values of \<service_type\>: `confd`, `ios`.
`processes/<fid>` | `{ "state": "<HA state>" }` | The items are created and updated by `hax` processes.  Supported values of \<HA state\>: `M0_CONF_HA_PROCESS_STARTING`, `M0_CONF_HA_PROCESS_STARTED`, `M0_CONF_HA_PROCESS_STOPPING`, `M0_CONF_HA_PROCESS_STOPPED`.
`timeout` | YYYYmmddHHMM.SS | This value is used by the RC timeout mechanism.

<!--
  XXX TODO: s/processes/m0-servers/

  Word "process" is ambiguous, we should be more specific.
  We are dealing with a subset of m0_conf_process objects.
  The items correspond to m0d processes --- Mero servers.

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
