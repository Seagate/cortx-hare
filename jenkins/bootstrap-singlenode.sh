#!/usr/bin/env bash
set -e -o pipefail
set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

# NOTE: cortx-hare have to be installed: either RPM or devinstall

usermod --append --groups hare ${USER}
mkdir -p /var/motr
echo "options lnet networks=tcp(eth1) config_on_load=1" > /etc/modprobe.d/lnet.conf
for i in {0..9}; do
    dd if=/dev/zero of=/var/motr/disk${i}.img bs=1M seek=9999 count=1
    losetup /dev/loop${i} /var/motr/disk${i}.img
done
# XXX-FIXME: to discuss
hctl bootstrap --mkfs /opt/seagate/cortx/hare/share/cfgen/examples/singlenode.yaml
