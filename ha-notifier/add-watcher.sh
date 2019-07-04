#!/bin/bash

consul watch -type=keyprefix -prefix=BQ 'bq/listener.py 0@lo:12345:34:101'
