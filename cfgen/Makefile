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
 diff -u - <(grep -E "^.(controller-7\
|drive-(1[13579]|2[13]|71)\
|enclosure-5\
|node\
|objv-(5[0-9]|6[015-8]|7[2-6])\
|pool-(1|48|69)\
|process-(2[47]|3[08]|4[0246])\
|profile-77\
|pver-(2|49|63)\
|pver_f\
|rack-4\
|root\
|sdev-(1[02468]|2[02]|70|8)\
|service-(2[5689]|3[1-79]|4[1357])\
|site)\>" _misc/conf.cg | xcode)
