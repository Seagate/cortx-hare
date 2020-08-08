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

# Contributing

## The process
This project uses
[PC3 (Pedantic Code Construction Contract)](rfc/9/README.md)
process for contributions.  
Read it to learn contribution requirements and
process details.

## Basic scenario
* Create github issue in Seagate repo or pick existing one. Issue contains problem description and holds discussion if needed.
* Create dedicated branch with meaningful name in personal fork.
* Once patch is ready rebase it on top of Seagate/dev branch.
* Check patch for conformance to PC3, create pull request to dev branch of Seagate repository.
* Add reference to existing issue to pull request and assign to one of suggested reviewers.
* Be responsive to reviewer requests in order to clarify details and improve the patch if needed.

## See also:
* Bootstrap guide: [README.md](README.md): _how to get source code and run hare + motr instance_.
* Developers guide: [Developers guide](README_developers.md): _how to build and install from sources_.
* Product design and API documentation: [RFCs](rfc/)
