SHELL = /bin/bash

M0_SRC_DIR ?= ../../mero

CPPFLAGS := -I$(M0_SRC_DIR) $(shell python-config --includes)
CPPFLAGS += -DM0_INTERNAL= -DM0_EXTERN=extern

CFLAGS := -g -Werror -Wno-attributes
# CFLAGS += -Wall -Wextra
CFLAGS += -fPIC

LDFLAGS = -shared
LDLIBS = $(shell python-config --libs) -L$(M0_SRC_DIR)/mero/.libs -lmero

hax.so: hax.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(LDLIBS) $^ -o $@

.PHONY: clean
clean:
	rm -f hax.so
