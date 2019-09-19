---
domain: gitlab.mero.colo.seagate.com
shortname: 3/CFGEN
name: Configuration Generation
status: draft
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Andriy Tkachuk <andriy.tkachuk@seagate.com>
---

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in
[RFC 2119](https://tools.ietf.org/html/rfc2119).

## Configuration Generation

Configuration generation script &mdash; `cfgen` &mdash; generates
various configuration files required to start Mero cluster.

![cfgen](cfgen.png)

### Cluster Description File (CDF)

Cluster administrator SHALL provide a _cluster description file_ (CDF),
specifying which hosts the cluster is made of, how many Mero services
and clients to run, where to run confd services, which drives to use
for Mero I/O.

CDF is a YAML file with the following schema:
```yaml
hosts:
  - name: <str>  # [user@]hostname; e.g., localhost, samir@10.22.33.44
    data_iface: <str>   # ipaddress correspond to this interface to be used for
                        # data services (mero services). This is optional and
                        # default ip address will be used if not specified.
    disks:
    m0_servers:
      - runs_confd: <bool>  # optional, defaults to false
        #io_disks: null                 # no IO service
        io_disks: { path_glob: <str> }  # e.g. "/dev/loop[0-9]*"
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

### `cfgen` script

```
usage: cfgen [-o <output-dir>] [--mock]

Generate configuration files required to start Mero cluster.

optional arguments:
  -h, --help           show this help message and exit
  --help-schema        show cluster description file schema
  -D dir, --dhall dir  directory with auxiliary Dhall expressions (defaults to
                       '/opt/cfgen/dhall')
  -o output-dir        output directory (defaults to '.')
  --mock               Generate pseudo-random "facts". The hosts specified in
                       the cluster description file will not be visited and
                       don't even have to exist.
  --debug              print the enriched cluster description and exit
  -V, --version        show program's version number and exit

The program reads cluster description in YAML format from the standard input;
'--help-schema' option shows the schema.
```

**cfgen** reads the CDF from stdin, ssh-es to the hosts mentioned in it,
collects their "facts" (e.g., number of CPUs, RAM size), and uses that
information to generate configuration data.

### Output files

  * `consul-agents.json` &mdash; tells [`bootstrap`](rfc/6/README.md) script
    where Consul server and client agents should be started and which
    IP addresses they should bind to.

    Format:
    ```
    {
      "servers": [
        {
          "hostname": "<str>",
          "ipaddr": "<str>"
        }
      ],
      "clients": [
        {
          "hostname": "<str>",
          "ipaddr": "<str>"
        }
      ]
    }
    ```
    `"servers"` list MUST NOT be empty.

  * `consul-kv.json` &mdash; key/value pairs in JSON format, ready to be
    consumed by
    [`consul kv import`](https://www.consul.io/docs/commands/kv/import.html).

  * `confd.xc` &mdash; Mero configuration in xcode string format, ready to
    be used by confd services.
