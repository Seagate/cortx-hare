#!/bin/bash

set -x

CWD="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
MERODIR=${MERODIR:-"${CWD}/../../mero"}
LIBMERO="${MERODIR}/mero/.libs/"

gcc  ./hax.c \
  $(python-config --includes) \
  $(python-config --libs) \
  -I ${MERODIR} -L ${LIBMERO} -lmero -Wno-attributes -Werror -g -DM0_INTERNAL= -DM0_EXTERN=extern \
  -shared \
  -fPIC \
  -o ./hax.so
