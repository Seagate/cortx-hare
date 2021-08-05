#!/bin/bash
set -ex

source ./.py-venv/bin/activate

# Disabled for now because of errors in cortx-ha sources
#MYPYPATH=cortx-ha/ mypy ./emitter.py
flake8 ./emitter.py
python ./emitter.py
