---
domain: gitlab.mero.colo.seagate.com
shortname: 3/CONFGEN
name: Configuration Generation
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Configuration Generation

![m0conf](m0conf.png)

### `collect-facts`

```
Usage: collect-facts [--mock] [-o <output-dir>] [--singlenode]

Options:

  -o <output-dir>  Directory to store generated files in; defaults to
                   `cluster-facts/`.
  --singlenode  Gather information about local host only.
  --mock        Generate pseudo-random facts.  The hosts specified in
                <cluster-desc> file are not visited and don't even have
                to exist.
  -h, --help    Show this help and exit.

When executed without `--singlenode` option, the program reads cluster
description file from standard input.  This should be YAML file with
the following schema:

XXX TODO
```

**collect-facts** ssh-es to the hosts mentioned in the cluster description file, collects "facts" about them (e.g., `facter --json processors | jq .processors.count`, `facter memorysize_mb`) and saves that data locally as [Dhall](https://dhall-lang.org/) expressions (`cluster-facts/*.dhall`).

### `m0conf`

**m0conf** runs a particular Dhall processing pipeline, selected via CLI option.

`m0conf --confd` outputs Mero configuration in xcode string format, ready to be consumed by confd services.

`m0conf --kv` outputs KV pairs in JSON format, ready to be consumed by [`consul kv import`](https://www.consul.io/docs/commands/kv/import.html).

`m0conf --etc m0d` outputs /etc configuration for m0d process.
