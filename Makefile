SHELL = bash

PYTHON_SCRIPTS = cluster-shutdown cluster-status
MYPY_OPTS = --config-file hax/mypy.ini

.PHONY: check
check: flake8 typecheck

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	flake8 $(FLAKE8_OPTS) $^

.PHONY: typecheck
typecheck: $(PYTHON_SCRIPTS)
	set -eu -o pipefail; for f in $^; do mypy $(MYPY_OPTS) $$f; done

