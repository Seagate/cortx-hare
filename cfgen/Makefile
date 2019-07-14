SHELL = bash

PYTHON_SCRIPTS = collect-facts cfgen

# XXX YMMV
M0_SRC_DIR = ~/src/mero

.PHONY: check
check: flake8 typecheck

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	flake8 $(FLAKE8_OPTS) $^

.PHONY: typecheck
typecheck: $(PYTHON_SCRIPTS)
	set -e -o pipefail; for f in $^; do mypy $$f; done

.PHONY: check-dhall
check-dhall: confd.dhall
	xcode() { sort | $(M0_SRC_DIR)/utils/m0confgen; };\
 dhall-to-text < $< | xcode |\
 diff -u - <(grep -E '^.(root|node|process-24)\>' _misc/conf.cg | xcode)
