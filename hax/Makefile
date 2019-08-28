SHELL = /bin/bash

M0_SRC_DIR ?= ../../mero

CPPFLAGS := -I$(M0_SRC_DIR) $(shell python-config --includes)
CPPFLAGS += -DM0_INTERNAL= -DM0_EXTERN=extern

CFLAGS = -g -Werror -Wall -Wextra -Wno-attributes -Wno-unused-parameter -fPIC

LDFLAGS = -shared
LDLIBS = $(shell python-config --libs) -L$(M0_SRC_DIR)/mero/.libs -lmero

SRC_DIR = hax

SRC = $(SRC_DIR)/hax.c

SONAMES := $(SRC:$(SRC_DIR)/%.c=$(SRC_DIR)/lib%.so.0)
SYMLINKS := $(basename $(SONAMES))  # strip version suffix

all: $(SONAMES) $(SYMLINKS)

OBJ := $(SRC:.c=.o)
-include $(OBJ:.o=.d)

# Generate dependencies.
$(SRC_DIR)/%.d: $(SRC_DIR)/%.c
	cpp -MM -MG $(CPPFLAGS) $< |\
 sed -r 's%^(.+)\.o:%$(@D)/\1.d $(@D)/\1.o:%' >$@

$(SRC_DIR)/%.so: $(SRC_DIR)/%.so.0
	ln -s $(notdir $^) $@

$(SRC_DIR)/lib%.so.0: $(SRC_DIR)/%.o
	$(CC) $(LDFLAGS) -Wl,-soname,$@ $^ -o $@
# Output file should be versioned.
# See http://tldp.org/HOWTO/Program-Library-HOWTO/shared-libraries.html#AEN95

.PHONY: mostlyclean
mostlyclean:
	rm -f $(OBJ) $(OBJ:.o=.d)

.PHONY: clean
clean: mostlyclean
	rm -f $(SONAMES) $(SYMLINKS)
