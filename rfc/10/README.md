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

See: [3/CFGEN](rfc/3/README.md)

<!-- XXX Other definitions that we might want to add:

     - cfgen
     - ? cluster
     - hax
 -->

## See also

* [RFC 1983](https://www.rfc-editor.org/rfc/rfc1983.html)
