#!/bin/bash

# Recovery Coordinator (RC) prototype.
#
# Impletemnted as a Consul watcher handler over the Events Queue (EQ)
# in the persistent KV-store.
#
# Takes the JSON array of events from stdin and process them one after
# another. Each event is deleted from the queue after processing.
#
# NOTE: depends on jq >= 1.6 - https://stedolan.github.io/jq
#
# Run it like this:
#
# $ consul watch -type=keyprefix -prefix eq/ proto-rc.sh
#

cat | sed 's/null//' | jq -r '.[] | "\(.Key) \(.Value | @base64d)"' | while
  read EPOCH EVENT; do
    echo "RC: $CONSUL_INDEX: Process $EPOCH $EVENT..."
    sleep 10
    consul kv delete $EPOCH
  done
