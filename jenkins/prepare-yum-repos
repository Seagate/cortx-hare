#!/usr/bin/env bash
#
# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

set -e -o pipefail
# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

export
MOTR_REPO_FILE=/etc/yum.repos.d/motr_last_successful.repo
LUSTRE_REPO_FILE=/etc/yum.repos.d/lustre_release.repo

cat <<EOT > $MOTR_REPO_FILE
[motr-dev]
baseurl=http://cortx-storage.colo.seagate.com/releases/eos/github/release/rhel-7.7.1908/last_successful/
gpgcheck=0
name=motr-dev
enabled=1
EOT

cat <<EOT > $LUSTRE_REPO_FILE
[lustre]
baseurl=http://cortx-storage.colo.seagate.com/releases/eos/lustre/lustre-2.12.3/
gpgcheck=0
name=lustre
enabled=1
EOT
