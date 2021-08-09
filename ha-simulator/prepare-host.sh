#!/bin/bash

# This script performs all the necessary actions to get Hare working against simulated HA and dockerized Kafka.

set -e -x

if [[ ! -f /etc/cortx/ha/ha.conf ]]; then
  sudo mkdir -p /etc/cortx/ha/
  sudo cp -fv docker/etc/ha.conf /etc/cortx/ha/ha.conf
fi


if [[ ! -f /etc/cortx/ha/ha.conf ]]; then
  sudo mkdir -p /etc/cortx/ha/
  sudo cp -f docker/etc/ha.conf /etc/cortx/ha/ha.conf
fi

#if [[ -f /etc/cortx/message_bus.conf ]]; then
  #echo '/etc/cortx/message_bus.conf already exists. Please rename or remove it' >&2
  #exit 1
#fi

cat <<EOF | sudo tee /etc/cortx/message_bus.conf > /dev/null
{
  "message_broker": {
    "type": "kafka",
    "message_bus": {
      "recv_message_timeout": "1000",
      "controller_socket_timeout": "1000",
      "send_message_timeout": "1000"
    },
    "cluster": [
      {
        "server": "ssc-vm-g2-rhev4-0175.colo.seagate.com",
        "port": "9093"
      }
    ]
  }
}
EOF
