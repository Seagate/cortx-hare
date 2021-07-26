---
domain: github.com
shortname: 18/CFGEN
name: Configuration Generation
status: draft
obsoletes: 3/CFGEN
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
contributors:
  - Rajanikant Chirmade <rajanikant.chirmade@seagate.com>
---

# Configuration Generation

Configuration generation script &mdash; `cfgen` &mdash; generates various configuration files required to start Motr cluster.

![cfgen](cfgen.png)

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://tools.ietf.org/html/rfc2119).

### Cluster Description File (CDF)

Cluster administrator SHALL provide a _cluster description file_ (CDF), specifying which hosts the cluster is made of, how many Motr services and clients to run, where to run confd services, which drives to use for Motr I/O.

CDF is a YAML file with the following schema:
```yaml
nodes:
  - hostname: <str>    # [user@]hostname; e.g., localhost, pod-c1
    data_iface: <str>  # name of network interface; e.g., eth1, eth1:c1
    data_iface_type: tcp|o2ib  # type of network interface;
                               # optional, defaults to "tcp"
    m0_servers:        # optional for client-only nodes
      - runs_confd: <bool>  # optional, defaults to false
        io_disks:
          meta_data: <str>  # device path for meta-data;
                            # optional, Motr will use "/var/motr/m0d-<FID>/"
                            # by default
          data: [ <str> ]   # e.g. [ "/dev/loop0", "/dev/loop1", "/dev/loop2" ]
                            # Empty list means no IO service.
    m0_clients:
        s3: <int>     # number of S3 servers to start
        other: <int>  # max quantity of other Motr clients this host may have
pools:
  - name: <str>
    type: sns|dix|md   # optional, defaults to "sns";
                       # "sns" - data pool, "dix" - KV, "md" - meta-data pool.
    data_units: <int>
    parity_units: <int>
    allowed_failures:  # optional section; no failures will be allowed
                       # if this section is missing or all of its elements
                       # are zeroes
      site: <int>
      rack: <int>
      encl: <int>
      ctrl: <int>
      disk: <int>
```

### `cfgen` script

```
usage: cfgen [OPTION]... CDF

Generate configuration files required to start Motr cluster.

positional arguments:
  CDF                  cluster description file; use '--help-schema' option
                       for format description

optional arguments:
  -h, --help           show this help message and exit
  --help-schema        show the schema of cluster description file (CDF)
  -D dir, --dhall dir  directory with auxiliary Dhall expressions (defaults to
                       '/opt/seagate/cortx/hare/share/cfgen/dhall')
  -o output-dir        output directory (defaults to '.')
  --mock               Generate pseudo-random "facts". The hosts specified in
                       the cluster description file will not be visited and
                       don't even have to exist.
  --debug              print the enriched cluster description and exit
  -V, --version        show program's version number and exit
```

**cfgen** reads the CDF, ssh-es to the hosts mentioned in it, collects their "facts" (e.g., number of CPUs, RAM size), and uses that information to generate configuration data.

### Output files

  * `confd.dhall` &mdash; Motr configuration in [Dhall](https://dhall-lang.org/) format.

  * `consul-agents.json` &mdash; tells [`bootstrap`](rfc/6/README.md) script where Consul server and client agents should be started and which IP addresses they should bind to.

    Format:
    ```
    {
      "servers": [
        {
          "node_name": "<str>",
          "ipaddr": "<str>"
        }
      ],
      "clients": [
        {
          "node_name": "<str>",
          "ipaddr": "<str>"
        }
      ]
    }
    ```
    `"servers"` list MUST NOT be empty.

  * `consul-kv.json` &mdash; key/value pairs in JSON format, ready to be
    consumed by
    [`consul kv import`](https://www.consul.io/docs/commands/kv/import.html).
