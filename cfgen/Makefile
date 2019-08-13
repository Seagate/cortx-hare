SHELL = bash

PYTHON_SCRIPTS = collect-facts cfgen

# XXX YMMV
M0_SRC_DIR = ~/src/mero

.PHONY: check
check: flake8 typecheck test-collect-facts

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	flake8 $(FLAKE8_OPTS) $^

.PHONY: typecheck
typecheck: $(PYTHON_SCRIPTS)
	set -eu -o pipefail; for f in $^; do mypy $$f; done

.PHONY: check-dhall
check-dhall: confd.dhall
	xcode() { sort | $(M0_SRC_DIR)/utils/m0confgen; };\
 dhall text < $< | xcode |\
 diff -u - <(xcode <_misc/conf.cg)

.PHONY: test-collect-facts
test-collect-facts:
	set -eu -o pipefail;\
 out=/tmp/cfgen-out;\
 sed s/loop.*]/disk2/ ./_misc/singlenode.yaml |\
 ./collect-facts --mock -o $$out;\
 awk '/XXX/ {print "--", $$0; next} $$1 == "," && !p {$$1 = "["; p=1} {print}'\
 $$out/confd.dhall | dhall text | $(M0_SRC_DIR)/utils/m0confgen >/dev/null
