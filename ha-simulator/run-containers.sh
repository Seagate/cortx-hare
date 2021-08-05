#!/bin/bash

set -e -x
#docker-compose up -d consul
docker-compose up -d kafka zookeeper
