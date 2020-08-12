#!/usr/bin/env bash
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
