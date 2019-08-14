---
domain: gitlab.mero.colo.seagate.com
shortname: 6/BOOT
name: Mero Cluster Bootstrapping
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Mero Cluster Bootstrapping

Cluster administrator

1. Prepares the
   [cluster description file](rfc/3/README.md#cluster-description-file).

1. Runs `bootstrap` script (on any cluster node), passing the cluster
   description file to it via standard input.

The `bootstrap` script

1. Executes [‘cfgen’ script](rfc/3/README.md#cfgen), which generates
   `consul-nodes`, `consul-services.json`, `consul-kv.json`, and
   `confd.xc` files.

1. Starts `consul` agents, knowing from `consul-nodes` file where
   server and client agents should be running.

1. Initialises [Consul KV](rfc/4/README.md) by executing
   `consul kv import @consul-kv.json` command.

1. Starts `hax` on each of the nodes.  Each of the `hax` processes
   gets its [three fids](#8) from the Consul KV.

1. Starts `m0mkfs` processes.

   XXX TBD: We should be able to use Consul watch(es) to notify
   ‘bootstrap’ the completion of `m0mkfs`.  E.g., ‘bootstrap’ may
   wait for a file, which will be created by a Consul's watch
   handler.  Once `m0mkfs` has completed on a node with Consul
   server agent, ‘bootstrap’ may proceed with starting confd on that
   node.

1. Uploads `confd.xc` file to the Consul server nodes (those listed in
   the `[servers]` section of `consul-nodes` file).  Starts “confd”
   `m0d` on those nodes.

1. Starts the rest of `m0d`s (I/O services), obtaining the names of
   their hosts and CLI arguments (?) from the Consul KV.
