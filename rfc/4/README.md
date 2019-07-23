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

### Entrypoint Reply Data

```c
struct m0_ha_entrypoint_rep {
        uint32_t                        hae_quorum;            //XXX
        struct m0_fid_arr               hae_confd_fids;        //XXX
        const char                    **hae_confd_eps;
        struct m0_fid                   hae_active_rm_fid;     //XXX
        char                           *hae_active_rm_ep;      //XXX
        /** Data passed back to client to control query flow */
        enum m0_ha_entrypoint_control   hae_control;
        /* link parameters */
        struct m0_ha_link_params        hae_link_params;       //XXX
        bool                            hae_link_do_reconnect; //XXX
};
```
How do we obtain the data for the fields, marked with `//XXX`, from Clovis?

* entrypoint quorum?
* confd fids
* confd endpoint addresses
* primary RM fid
* primary RM endpoint address
