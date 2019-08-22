#!/usr/bin/env bash
set -eu -o pipefail

# Helper script to install the stuff on the local node

export SRC_DIR="$(dirname $(readlink -f $0))"

sudo mkdir -p /opt/seagate
sudo ln -sfn $SRC_DIR /opt/seagate/consul

sudo ln -sf $SRC_DIR/systemd/* /usr/lib/systemd/system/
sudo systemctl daemon-reload
