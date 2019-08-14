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
`epoch` | current epoch (natural number) | Atomically incremented counter, which is used to generate unique ordered identifiers for EQ and BQ entries.
`eq/<epoch>` | event | `eq/*` items are collectively referred to as the EQ (Event Queue).  Events are consumed and dequeued by the RC script.
`leader` | node name | This key is used for RC leader election.  Created with [`consul lock`](https://www.consul.io/docs/commands/lock.html) command.
`timeout` | YYYYmmddHHMM.SS | This value is used by the RC timeout mechanism.
