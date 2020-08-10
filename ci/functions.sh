die() {
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
#

    echo "$@" >&2
    exit 1
}

_time() {
    if [[ -x /usr/bin/time ]]; then
        /usr/bin/time "$@"
    else
        time "$@"
    fi
}

ci_vm_name_prefix() {
    # XXX Here we rely on the fact that the script that sources
    # functions.sh has the same name as the CI job.  This is fragile.
    echo "${WORKSPACE_NAME}-${CI_JOB_NAME:-${0##*/}}"
}

ci_init_m0vg() (
    [[ $M0VG == m0vg-$CI_JOB_NAME/scripts/m0vg ]] ||
        die "${FUNCNAME[0]}: Invalid M0VG"

    local hosts=
    case $CI_JOB_NAME in
        test-boot1)
            hosts=(cmu)
            ;;
        test-boot2)
            hosts=(ssu1 ssu2)
            ;;
        test-boot3)
            hosts=(ssu1 ssu2 ssu3)
            ;;
        *) "${FUNCNAME[0]}: Invalid CI_JOB_NAME";;
    esac

    cd $WORKSPACE_DIR

    if [[ ! -x $M0VG ]]; then
        # Get `m0vg` script.
        #
        # Notes:
        # 1. We download the latest Motr, disregarding `MERO_COMMIT_REF`.
        # 2. We use no `--recursive`, because we don't need submodules.
        git clone --depth 1 http://gitlab.mero.colo.seagate.com/mero/mero.git \
            ${M0VG%%/*}
    fi

    $M0VG env add <<EOF
M0_VM_BOX=centos77/dev
M0_VM_BOX_URL='http://ci-storage.mero.colo.seagate.com/vagrant/centos77/dev'
M0_VM_CMU_MEM_MB=4096
M0_VM_NAME_PREFIX=$(ci_vm_name_prefix)
M0_VM_HOSTNAME_PREFIX=$(ci_vm_name_prefix)
M0_VM_SSU_NR=3
EOF

    local host=
    for host in ${hosts[@]}; do
        _time $M0VG up --no-provision $host
        _time $M0VG reload --no-provision $host
    done

    # 'hostmanager' plugin should be executed last, when all machines are up.
    for host in ${hosts[@]}; do
        $M0VG provision --provision-with hostmanager $host
    done
)

ci_success() {
    # `expect-timeout` expects this message as a test success criteria.
    echo "$CI_JOB_NAME: test status: SUCCESS"
}

XXX_with_s3server() {
    if [[ -n ${MERO_COMMIT_REF:-} ]]; then
        cat >&2 <<'EOF'
*WARNING* CI cannot test s3server with custom Motr.
See http://gitlab.mero.colo.seagate.com/mero/hare/issues/216
EOF
        return 1
    else
        return 0
    fi
}
