PYTHON_SOURCES = genconf

# XXX YMMV
M0_SRC_DIR = ~/src/mero

SHELL = bash

.PHONY: all
all: typecheck pep8

.PHONY: typecheck
typecheck: $(PYTHON_SOURCES)
	mypy $^

.PHONY: pep8
pep8: $(PYTHON_SOURCES)
	pycodestyle $^

.PHONY: check-dhall
check-dhall: m0conf.dhall
	xcode() { sort | $(M0_SRC_DIR)/utils/m0confgen; };\
 dhall-to-text < $< | xcode |\
 diff -u - <(grep -E '^.(root|node|process-24)\>' _misc/conf.cg | xcode)
