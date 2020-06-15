#!/usr/bin/env bash
set -e -o pipefail
# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

export
MERO_REPO_FILE=/etc/yum.repos.d/motr_last_successful.repo
LUSTRE_REPO_FILE=/etc/yum.repos.d/lustre_release.repo

cat <<EOT > $MERO_REPO_FILE
[motr-dev]
baseurl=http://ci-storage.mero.colo.seagate.com/releases/eos/components/github/master/rhel-7.7.1908/dev/mero/last_successful/
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
