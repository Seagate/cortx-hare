#!/bin/bash

# [KN] Note that we don't base64-encode the file by ourselves - this is done by consule under the hood
# Although the value will be read undecoded afterwards (i.e. we'll need to decode it in the listener)

curl -X PUT --data-binary @test.yaml http://127.0.0.1:8500/v1/kv/BQ/1

