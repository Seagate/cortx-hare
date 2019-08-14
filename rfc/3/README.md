---
domain: gitlab.mero.colo.seagate.com
shortname: 3/CFGEN
name: Configuration Generation
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in
[RFC 2119](https://tools.ietf.org/html/rfc2119).

## Configuration Generation

![cfgen](cfgen.png)

### Cluster Description File

Cluster administrator SHALL provide a _cluster description file_,
specifying which hosts the cluster is made of, how many Mero services
and clients to run, where to run confd services, which drives to use
for Mero I/O.

The file is in YAML format and has the following schema:
```yaml
hosts:
  - name: <str>  # [user@]hostname; e.g., localhost, samir@10.22.33.44
    disks: { path_glob: <str> }  # e.g. "/dev/loop[0-9]*"
    m0_servers:
      - runs_confd: <bool>   # optional, defaults to false
        io_disks:
          path_regex: <str>  # e.g. "."; empty string means no IO service
    c0_clients: <int>        # max quantity of Clovis apps this host may have
    m0t1fs_clients: <int>    # max quantity of m0t1fs clients
pools:
  - name: <str>
    allowed_failures:  # optional section; no failures will be allowed
                       # if this section is missing or all of its elements
                       # are zeroes
      site: <int>
      rack: <int>
      encl: <int>
      ctrl: <int>
      disk: <int>
    data_units: <int>
    parity_units: <int>
    #
    # There are two ways of assigning disks to pool.
    #
    # 1) Choose which disks of which host to use for this pool.
    disks:
      select:
        - { host: <str>, path_regex: <str> }
    # 2) Use all available disks of all hosts for this pool.
    #disks: all
```

### `collect-facts`

```
usage: collect-facts [-o <output-dir>] [--mock]

optional arguments:
  -h, --help     show this help message and exit
  --help-schema  show cluster description file schema
  -o output-dir  directory to store generated files in (defaults to
                 'collected-facts')
  --mock         Generate pseudo-random "facts". The hosts specified in the
                 cluster description file will not be visited and don't even
                 have to exist.
  -V, --version  show program's version number and exit

The program reads cluster description in YAML format from the standard input;
'--help-schema' option shows the schema.
```

**collect-facts** ssh-es to the hosts mentioned in the cluster
description file, collects "facts" about them (e.g.,
`facter --json processors | jq .processors.count`, `facter memorysize_mb`)
and saves that data locally as [Dhall](https://dhall-lang.org/) expressions
(`collected-facts/*.dhall`).

### `cfgen`

**cfgen** performs Dhall processing and generates the following files:

  * `consul-nodes` -- tells [`bootstrap`](rfc/6/README.md) script
    where Consul server and client agents should be started.

    Format:
    ```
    [servers]
    hostname
    hostname
    hostname

    [clients]
    hostname
    hostname

    # Comments start with a hash symbol and run to the end of the line.
    ```

  * `consul-services.json` -- Consul services and
    [watches](https://www.consul.io/docs/agent/watches.html)
    definitions.

  * `consul-kv.json` -- key/value pairs in JSON format, ready to be
    consumed by
    [`consul kv import`](https://www.consul.io/docs/commands/kv/import.html).

  * `confd.xc` -- Mero configuration in xcode string format, ready to
    be used by confd services.
