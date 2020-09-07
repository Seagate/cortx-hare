# Copyright (c) 2020 Seagate Technology LLC and/or its Affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

SHELL = bash -x

PYTHON_SCRIPTS = cfgen

M0CONFGEN := $(if\
 $(shell which m0confgen 2>/dev/null),m0confgen,../../motr/utils/m0confgen)

dhall-lang-version := $(shell readlink ../vendor/dhall-prelude/current)
dhall-lang-dir := dhall/dhall-lang-$(dhall-lang-version)

.PHONY: check
check: flake8 typecheck test-cfgen check-dhall

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	flake8 $(FLAKE8_OPTS) $^

.PHONY: typecheck
typecheck: $(PYTHON_SCRIPTS)
	set -eu -o pipefail; for f in $^; do MYPYPATH=../stubs mypy $$f; done

.PHONY: test-cfgen
test-cfgen: unpack-dhall-prelude
	set -eu -o pipefail;\
 out=$$(mktemp -d);\
 ./cfgen -D ./dhall --mock --debug examples/singlenode.yaml >/dev/null;\
 ./cfgen -D ./dhall --mock -o $$out examples/singlenode.yaml;\
 dhall text <$$out/confd.dhall | $(M0CONFGEN) >/dev/null;\
 jq . <$$out/consul-kv.json >/dev/null;\
 rm -r $$out

.PHONY: check-dhall
check-dhall: unpack-dhall-prelude
	for cdf in examples/*.yaml; do\
 yaml-to-dhall ./dhall/types/ClusterDesc.dhall <$$cdf >/dev/null; done
	yaml-to-dhall ./dhall/types/ClusterDesc.dhall <examples/singlenode.yaml\
 | dhall-to-yaml | diff -u - <(dhall-to-yaml <<<./tests/singlenode.dhall)
	xcode() { sort | $(M0CONFGEN); };\
 dhall text --file tests/sample-confd.dhall | xcode\
 | diff -u - <(xcode <tests/conf.cg)

.PHONY: unpack-dhall-prelude
unpack-dhall-prelude: $(dhall-lang-dir)/Prelude/package.dhall

$(dhall-lang-dir)/Prelude/package.dhall:
	tar -C dhall --no-same-owner -xzf\
 ../vendor/dhall-prelude/$(dhall-lang-version)/v$(dhall-lang-version).tar.gz\
 dhall-lang-$(dhall-lang-version)/Prelude

.PHONY: clean-dhall-prelude
clean-dhall-prelude:
	rm -rf $(dhall-lang-dir)

.PHONY: clean
clean: clean-dhall-prelude
