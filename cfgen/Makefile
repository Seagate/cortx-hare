SHELL = bash

PYTHON_SCRIPTS = cfgen

# XXX YMMV
M0_SRC_DIR = ~/src/mero

.PHONY: check
check: flake8 typecheck test-cfgen check-dhall

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	flake8 $(FLAKE8_OPTS) $^

.PHONY: typecheck
typecheck: $(PYTHON_SCRIPTS)
	set -eu -o pipefail; for f in $^; do mypy $$f; done

.PHONY: test-cfgen
test-cfgen:
	set -eu -o pipefail;\
 out=$$(mktemp -d);\
 ./cfgen --mock -o $$out --dhall ./dhall <_misc/singlenode.yaml;\
 dhall text <$$out/confd.dhall | $(M0_SRC_DIR)/utils/m0confgen >/dev/null;\
 rm -r $$out

.PHONY: check-dhall
check-dhall: _misc/sample-confd.dhall
	xcode() { sort | $(M0_SRC_DIR)/utils/m0confgen; };\
 dhall text < $< | xcode |\
 diff -u - <(xcode <_misc/conf.cg)
