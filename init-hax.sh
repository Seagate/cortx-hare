#!/usr/bin/env bash
set -x -e -o pipefail

HARE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ENV_DIR="${HARE_DIR}/.env/"

python3 -m venv ${ENV_DIR}

source ${ENV_DIR}/bin/activate
pip install -r ${HARE_DIR}/hax/requirements.txt

