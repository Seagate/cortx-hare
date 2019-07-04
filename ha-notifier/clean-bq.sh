#!/bin/bash

consul kv get -recurse BQ | sed 's/^\([^:]*\).*$/\1/g' | xargs -n1 consul kv delete 

