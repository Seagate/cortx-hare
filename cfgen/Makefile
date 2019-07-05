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
 diff -u - <(grep -E '^.(controller-7|enclosure-5|rack-4|root|node|process-24|process-27|process-30|process-38|process-40|process-42|process-44|process-46|service-25|service-26|service-28|service-29|service-31|service-32|drive-11|drive-13|drive-15|drive-17|drive-19|drive-21|drive-23|drive-71|service-33|service-34|service-35|service-36|service-37|service-39|service-41|service-43|service-45|service-47|pool-1|pool-48|pool-69|pver-2|pver-49|pver-63|sdev-8|sdev-10|sdev-12|sdev-14|sdev-16|sdev-18|sdev-20|sdev-22|sdev-70|pver_f|drive-17|objv-50|objv-51|objv-52|objv-53|objv-54|objv-55|objv-56|objv-57|objv-58|objv-59|objv-60|objv-61|objv-65|objv-66|objv-67|objv-68|objv-72|objv-73|objv-74|objv-75|objv-76|objv-68|profile-77|site)\>' _misc/conf.cg | xcode)
