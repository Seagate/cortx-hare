die() {
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

# CAUTION: ci_job_label cannot be used in "m0vg" environment, because
# WORKSPACE_NAME and CI_JOB_NAME are not defined there.
ci_job_label() {
    echo "${WORKSPACE_NAME}-${CI_JOB_NAME}"
}

ci_init_m0vg() (
    case $# in
        1) local m0vg_dir=m0vg-1node;;
        2) local m0vg_dir=m0vg-2nodes;;
        *) die "Usage: ${FUNCNAME[0]} HOST [HOST_2]";;
    esac
    [[ $M0VG == $m0vg_dir/scripts/m0vg ]] ||
        die "${FUNCNAME[0]}: Impossible happened"

    cd $WORKSPACE_DIR

    if [[ ! -d $m0vg_dir ]]; then
        # Get `m0vg` script ($m0vg_dir/scripts/m0vg).
        # Note that we download the latest Mero, disregarding
        # `MERO_COMMIT_REF`.
        git clone --recursive --depth 1 --shallow-submodules \
            http://gitlab.mero.colo.seagate.com/mero/mero.git $m0vg_dir
    fi

    $M0VG env add <<EOF
M0_VM_BOX=centos76/dev
M0_VM_BOX_URL='http://ci-storage.mero.colo.seagate.com/vagrant/centos76/dev'
M0_VM_CMU_MEM_MB=4096
M0_VM_NAME_PREFIX=$(ci_job_label)
M0_VM_HOSTNAME_PREFIX=$(ci_job_label)
EOF

    local host=
    for host in "$@"; do
        _time $M0VG up --no-provision $host
        _time $M0VG reload --no-provision $host
    done
)

ci_success() {
    # `expect-timeout` expects this message as a test success criteria.
    echo "$CI_JOB_NAME: test status: SUCCESS"
}

XXX_with_s3server() {
    if [[ -n ${MERO_COMMIT_REF:-} ]]; then
        cat >&2 <<'EOF'
*WARNING* CI cannot test s3server with custom Mero.
See http://gitlab.mero.colo.seagate.com/mero/hare/issues/216
EOF
        return 1
    else
        return 0
    fi
}
