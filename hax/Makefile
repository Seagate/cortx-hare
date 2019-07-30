SHELL = /bin/bash

M0_SRC_DIR ?= ../../mero

CPPFLAGS := -I$(M0_SRC_DIR) $(shell python-config --includes)
CPPFLAGS += -DM0_INTERNAL= -DM0_EXTERN=extern

CFLAGS := -g -Werror -Wno-attributes
# CFLAGS += -Wall -Wextra
CFLAGS += -fPIC

LDFLAGS = -shared
LDLIBS = $(shell python-config --libs) -L$(M0_SRC_DIR)/mero/.libs -lmero

SRC = hax.c

SONAMES := $(SRC:%.c=lib%.so.0)
SYMLINKS := $(basename $(SONAMES))  # strip version suffix

all: $(SONAMES) $(SYMLINKS)

OBJ := $(SRC:.c=.o)
-include $(OBJ:.o=.d)

# Generate dependencies.
%.d: %.c
	cpp -MM -MG $(CPPFLAGS) $< |\
 sed -r 's%^(.+)\.o:%$(@D)/\1.d $(@D)/\1.o:%' >$@

%.so: %.so.0
	ln -s $^ $@

lib%.so.0: %.o
	$(CC) $(LDFLAGS) -Wl,-soname,$@ $^ -o $@
# Output file should be versioned.
# See http://tldp.org/HOWTO/Program-Library-HOWTO/shared-libraries.html#AEN95

hax.so: hax.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(LDLIBS) $^ -o $@
libhax.so: hax.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(LDLIBS) $^ -o $@

.PHONY: mostlyclean
mostlyclean:
	rm -f $(OBJ) $(OBJ:.o=.d)

.PHONY: clean
clean: mostlyclean
	rm -f $(SONAMES) $(SYMLINKS)
