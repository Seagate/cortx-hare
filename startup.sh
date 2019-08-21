#!/usr/bin/env bash
set -eu -o pipefail

HARE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
MERO_SRC_DIR="${HARE_DIR}/../mero"

[ -d $HARE_DIR/.env ] || $HARE_DIR/init-hax.sh 

echo "Starting mero"
sudo modprobe lnet
sudo insmod $MERO_SRC_DIR/extra-libs/gf-complete/src/linux_kernel/m0gf.ko
sudo insmod $MERO_SRC_DIR/m0mero.ko

CONSUL_LOG_PATH=$HARE_DIR/consul-output.log

echo "Starting consul agent (the logs will be written to ${CONSUL_LOG_PATH})"
consul agent -bind='{{GetPrivateIP}}' \
             -server -config-dir=${HARE_DIR} \
             -data-dir=/tmp/consul -bootstrap-expect=1 \
             -client='127.0.0.1 {{GetPrivateIP}}' \
             -ui >>${CONSUL_LOG_PATH}  &

while ! consul kv get -keys / ; do
  sleep 1
done

$HARE_DIR/kv-init
$HARE_DIR/gen-service-ids

echo "Starting hax"
sudo LD_LIBRARY_PATH=$MERO_SRC_DIR/mero/.libs/ $HARE_DIR/env/bin/python $HARE_DIR/hax/hax.py

