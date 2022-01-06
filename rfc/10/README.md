---
domain: github.com
shortname: 10/GLOSS
name: Hare User's Glossary
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

There are many networking glossaries in existence.  This glossary
concentrates on terms which are specific to the Hare software.

## Glossary

### CDF

See: Cluster Description File

### Cluster Description File (CDF)

A YAML file with description of hardware and software entities that
Hare software will work with.  CDF contains the minimum amount of data
required to get Hare going.  For example, Hare will obtain the IP
address of the given host by itself, but first it must be told which
host(s) to work with.

See: [CFGEN](https://github.com/Seagate/cortx-hare/blob/main/rfc/18/README.md)

<!-- XXX Other definitions that we might want to add:

     - cfgen
     - ? cluster
     - hax
 -->

## See also

* [RFC 1983](https://www.rfc-editor.org/rfc/rfc1983.html)
