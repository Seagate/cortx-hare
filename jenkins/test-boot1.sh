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

set -eu -o pipefail
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '
set -x

export PATH="/opt/seagate/cortx/hare/bin:$PATH"

do_io() {
    /opt/seagate/cortx/hare/libexec/m0crate-io-conf > _m0crate-io.yaml
    dd if=/dev/urandom of=/tmp/128M bs=1M count=128
    time m0crate -S _m0crate-io.yaml
}

test_cluster() {
    local cdf=$1

    time hctl bootstrap --mkfs $cdf
    do_io
    hctl reportbug
    time hctl shutdown

    time hctl bootstrap --conf-dir /var/lib/hare  # bootstrap on existing conf
    do_io
    hctl reportbug bundle-id /tmp
    time hctl shutdown
}

# XXX
cd /opt/seagate/cortx/hare/share/cfgen/examples/

for cdf in singlenode.yaml ci-boot1-2ios.yaml; do
    test_cluster $cdf
done
