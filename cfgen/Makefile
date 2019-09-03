SHELL = bash

PYTHON_SCRIPTS = cfgen

M0_SRC_DIR = ../../mero

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
 ./cfgen --mock -o $$out -D ./dhall <_misc/singlenode.yaml;\
 dhall text <$$out/confd.dhall | $(M0_SRC_DIR)/utils/m0confgen >/dev/null;\
 jq . <$$out/consul-kv.json >/dev/null;\
 rm -r $$out

.PHONY: check-dhall
check-dhall:
	yaml-to-dhall ./dhall/types/ClusterDesc.dhall <_misc/singlenode.yaml\
 | dhall-to-yaml | diff -u - <(dhall-to-yaml <<<./_misc/singlenode.dhall)
	xcode() { sort | $(M0_SRC_DIR)/utils/m0confgen; };\
 dhall text --file _misc/sample-confd.dhall | xcode\
 | diff -u - <(xcode <_misc/conf.cg)
