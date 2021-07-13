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

.PHONY: default
default: build

.PHONY: help
help:
	@echo 'General targets:'
	@echo '  build          - build binary components (hax)'
	@echo '  test           - run tests'
	@echo '  clean          - remove build artefacts'
	@echo '  distclean      - perform clean and remove Python virtual env'
	@echo '                   directory with all installed pip modules'
	@echo '  install        - system-wide installation, respects DESTDIR'
	@echo '  devinstall     - local installation in the development mode,'
	@echo '                   respects DESTDIR'
	@echo '  uninstall      - uninstall all components, respects DESTDIR'
	@echo
	@echo 'Code linters:'
	@echo '  check          - run `flake8` and `mypy` linters for Python code'
	@echo '  flake8         - run `flake8` for Python code'
	@echo '  mypy           - run `mypy` for Python code'
	@echo
	@echo 'Distribution targets:'
	@echo '  rpm            - build release rpm package'
	@echo '  dist           - generate source code distribution archive'
	@echo
	@echo 'Docker:'
	@echo '  docker-images  - build Docker images for CI environment'
	@echo '  docker-push    - upload local Hare images to Docker registry'
	@echo '  docker-clean   - remove local Hare images'

# Globals --------------------------------------------- {{{1
#

SHELL := bash

TOP_SRC_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PY_VENV_DIR := $(TOP_SRC_DIR).py3venv
PYTHON      := python3.6
PY_VENV     := source $(PY_VENV_DIR)/bin/activate
PIP         := $(PY_VENV); pip3
SETUP_PY    := $(PY_VENV); $(PYTHON) setup.py
PY3_VERSION := 36
PY3_VERSION_MINOR := $(shell grep -o . <<<$(PY3_VERSION) | tail -n1)
DHALL_VERSION := 1.26.1
DHALL_URL     := https://github.com/dhall-lang/dhall-haskell/releases/download/$(DHALL_VERSION)/dhall-$(DHALL_VERSION)-x86_64-linux.tar.bz2
DHALL_JSON_VERSION := 1.4.1
DHALL_JSON_URL     := https://github.com/dhall-lang/dhall-haskell/releases/download/$(DHALL_VERSION)/dhall-json-$(DHALL_JSON_VERSION)-x86_64-linux.tar.bz2
DHALL_PRELUDE_VERSION := 11.1.0
DHALL_PRELUDE_URL     := https://github.com/dhall-lang/dhall-lang/archive/v$(DHALL_PRELUDE_VERSION).tar.gz

# Build ----------------------------------------------- {{{1
#

.PHONY: build
build: hax miniprov
	@$(MAKE) --quiet check

.PHONY: hax
HARE_VERSION := $(shell cat VERSION)
HAX_WHL      := hax/dist/hax-$(HARE_VERSION)-cp$(PY3_VERSION)-cp$(PY3_VERSION)m-linux_x86_64.whl
hax: $(HAX_WHL)

HAX_SRC := $(wildcard hax/setup.py hax/hax/*.py hax/hax/motr/*.[ch] hax/hax/motr/*.py hax/hax/queue/*.py)
$(HAX_WHL): $(PY_VENV_DIR) $(HAX_SRC)
	@$(call _info,Building hax .whl package)
	@cd hax && $(SETUP_PY) bdist_wheel

.PHONY: miniprov
MP_VERSION := $(shell cat VERSION)
MP_WHL      := provisioning/miniprov/dist/hare_mp-$(MP_VERSION)-py3-none-any.whl
miniprov: $(MP_WHL)

MP_SRC := $(wildcard provisioning/miniprov/setup.py provisioning/miniprov/hare_mp/*.py provisioning/miniprov/hare_mp/dhall/*.dhall)
$(MP_WHL): $(PY_VENV_DIR) $(HAX_SRC)
	@$(call _info,Building miniprov .whl package)
	@cd provisioning/miniprov && $(SETUP_PY) bdist_wheel

$(PY_VENV_DIR): $(patsubst %,%/requirements.txt,cfgen hax provisioning/miniprov)
	@$(call _info,Initializing virtual env in $(PY_VENV_DIR))
	@$(PYTHON) -m venv --system-site-packages $@
	@$(call _info,Installing pip modules in virtual env)
	@for f in $^; do \
	     $(call _log,processing $$f); \
	     $(PIP) install --ignore-installed -r $$f; \
	 done

# Clean ----------------------------------------------- {{{1
#

.PHONY: distclean
distclean: clean
	@$(call _info,Cleaning python virtual env and pip modules)
	@if [[ -e $(PY_VENV_DIR) ]]; then \
	     $(call _log,removing $(PY_VENV_DIR)); \
	     rm -rf $(PY_VENV_DIR); \
	 fi
	@$(call _info,Cleaning cached vendor files)
	@if [[ -d vendor ]]; then \
	     $(call _log,removing vendor/ dir); \
	     rm -rf vendor/; \
	 fi

.PHONY: clean
clean: clean-hax clean-mypy clean-dhall-prelude clean-miniprov

.PHONY: clean-hax
clean-hax:
	@$(call _info,Cleaning hax)
	@for d in hax/build hax/dist hax/hax.egg-info hax/*.so \
		  hax/hax/__pycache__ hax/hax/motr/__pycache__ \
		  hax/hax/queue/__pycache__ hax/test/__pycache__; do \
	     if [[ -e $$d ]]; then \
	         $(call _log,removing $$d); \
	         rm -rf $$d; \
	     fi; \
	 done

.PHONY: clean-mypy
clean-mypy:
	@$(call _info,Cleaning mypy cache)
	@find . -type d -name .mypy_cache -printf '%P\n' | while read d; do \
	     $(call _log,removing $$d); \
	     rm -rf $$d; \
	 done

.PHONY: clean-dhall-prelude
clean-dhall-prelude:
	$(MAKE) --quiet -C cfgen clean-dhall-prelude

.PHONY: clean-miniprov
clean-miniprov:
	$(MAKE) --quiet -C provisioning/miniprov clean
# Install --------------------------------------------- {{{1
#

PREFIX            := opt/seagate/cortx/hare
CFGEN_EXE          = $(DESTDIR)/$(PREFIX)/bin/cfgen
CFGEN_SHARE        = $(DESTDIR)/$(PREFIX)/share/cfgen
CONSUL_LIBEXEC     = $(DESTDIR)/$(PREFIX)/libexec/consul
CONSUL_SHARE       = $(DESTDIR)/$(PREFIX)/share/consul
HARE_CONF          = $(DESTDIR)/$(PREFIX)/conf
HARE_CONF_LOG      = $(DESTDIR)/$(PREFIX)/conf/logrotate
HARE_LIBEXEC       = $(DESTDIR)/$(PREFIX)/libexec
HARE_RULES         = $(DESTDIR)/$(PREFIX)/rules
HAX_EXE            = $(DESTDIR)/$(PREFIX)/bin/hax
MP_EXE       	   = $(DESTDIR)/$(PREFIX)/bin/hare_setup
HAX_EGG_LINK       = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hax.egg-link
MP_EGG_LINK        = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hare_mp.egg-link
SYSTEMD_CONFIG_DIR = $(DESTDIR)/usr/lib/systemd/system
LOGROTATE_CONF_DIR = $(DESTDIR)/etc/logrotate.d
ETC_CRON_DIR       = $(DESTDIR)/etc/cron.hourly
MINIPROV_TMPL_DIR  = $(DESTDIR)/$(PREFIX)/conf/

# dhall-bin {{{2
vendor/dhall-bin/$(DHALL_VERSION)/dhall-$(DHALL_VERSION)-x86_64-linux.tar.bz2:
	@$(call _log,fetching dhall $(DHALL_VERSION) archive)
	@mkdir -p vendor/dhall-bin/$(DHALL_VERSION)
	@cd vendor/dhall-bin/$(DHALL_VERSION) && \
	 curl --location --remote-name $(DHALL_URL)

vendor/dhall-bin/$(DHALL_VERSION)/dhall-json-$(DHALL_JSON_VERSION)-x86_64-linux.tar.bz2:
	@$(call _log,fetching dhall-json $(DHALL_VERSION) archive)
	@mkdir -p vendor/dhall-bin/$(DHALL_VERSION)
	@cd vendor/dhall-bin/$(DHALL_VERSION) && \
	 curl --location --remote-name $(DHALL_JSON_URL)

vendor/dhall-bin/$(DHALL_VERSION)/bin/dhall: \
		vendor/dhall-bin/$(DHALL_VERSION)/dhall-$(DHALL_VERSION)-x86_64-linux.tar.bz2
	@$(call _log,unpacking dhall $(DHALL_VERSION) archive)
	@cd vendor/dhall-bin/$(DHALL_VERSION) && \
	 tar --no-same-owner -xmf dhall-$(DHALL_VERSION)-x86_64-linux.tar.bz2

vendor/dhall-bin/$(DHALL_VERSION)/bin/dhall-to-json: \
		vendor/dhall-bin/$(DHALL_VERSION)/dhall-json-$(DHALL_JSON_VERSION)-x86_64-linux.tar.bz2
	@$(call _log,unpacking dhall-json $(DHALL_VERSION) archive)
	@cd vendor/dhall-bin/$(DHALL_VERSION) && \
	 tar --no-same-owner -xmf dhall-json-$(DHALL_JSON_VERSION)-x86_64-linux.tar.bz2

.PHONY: unpack-dhall-bin
unpack-dhall-bin: \
		vendor/dhall-bin/$(DHALL_VERSION)/bin/dhall \
		vendor/dhall-bin/$(DHALL_VERSION)/bin/dhall-to-json
	@cd vendor/dhall-bin && ln -sfn $(DHALL_VERSION)/bin current

# dhall-prelude {{{2
vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION):
	@mkdir -p vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION)

vendor/dhall-prelude/current: vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION)
	@cd vendor/dhall-prelude && ln -sfn $(DHALL_PRELUDE_VERSION) current

vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION)/v$(DHALL_PRELUDE_VERSION).tar.gz: vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION)
	@$(call _log,fetching dhall-prelude $(DHALL_PRELUDE_VERSION) archive)
	@cd vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION) && \
	 curl --location --output v$(DHALL_PRELUDE_VERSION).tar.gz \
	      $(DHALL_PRELUDE_URL)

.PHONY: fetch-dhall-prelude
fetch-dhall-prelude: \
	vendor/dhall-prelude/$(DHALL_PRELUDE_VERSION)/v$(DHALL_PRELUDE_VERSION).tar.gz \
	vendor/dhall-prelude/current

.PHONY: unpack-dhall-prelude
unpack-dhall-prelude: fetch-dhall-prelude
	@$(MAKE) --quiet -C cfgen unpack-dhall-prelude

# install {{{2
.PHONY: install
install: install-dirs install-cfgen install-hax install-miniprov install-systemd install-vendor install-provisioning
	@$(call _info,Installing hare utils)
	@for f in utils/*; do \
	     $(call _log,copying $$f -> $(HARE_LIBEXEC)); \
	     install $$f $(HARE_LIBEXEC); \
	 done
	@$(call _info,Installing RC rules)
	@for f in rules/*; do \
	     $(call _log,copying $$f -> $(HARE_RULES)); \
	     install $$f $(HARE_RULES); \
	 done
	@$(call _log,copying hctl -> $(DESTDIR)/$(PREFIX)/bin)
	@install hctl $(DESTDIR)/$(PREFIX)/bin
	@$(call _log,linking hctl -> $(DESTDIR)/usr/bin)
	@install --verbose --directory $(DESTDIR)/usr/bin
	@ln -sf /$(PREFIX)/bin/hctl $(DESTDIR)/usr/bin
	@$(call _log,copying h0q -> $(DESTDIR)/$(PREFIX)/bin)
	@install utils/h0q $(DESTDIR)/$(PREFIX)/bin
	@$(call _log,linking h0q -> $(DESTDIR)/usr/bin)
	@ln -sf /$(PREFIX)/bin/h0q $(DESTDIR)/usr/bin
	@$(call _log,copying m0trace-prune -> $(ETC_CRON_DIR))
	@install utils/m0trace-prune $(ETC_CRON_DIR)
	@for f in provisioning/miniprov/hare_mp/templates/hare.* \
		  provisioning/setup.yaml ; do \
	     $(call _log,copying $$f -> $(MINIPROV_TMPL_DIR)); \
	     install $$f $(MINIPROV_TMPL_DIR); \
	 done

.PHONY: install-dirs
install-dirs:
	@for d in $(HARE_CONF) \
		  $(HARE_CONF_LOG) \
		  $(HARE_LIBEXEC) \
		  $(HARE_RULES) \
		  $(ETC_CRON_DIR) \
		  $(DESTDIR)/run/cortx \
		  $(DESTDIR)/var/log/seagate/hare \
		  $(DESTDIR)/etc/logrotate.d \
		  $(DESTDIR)/var/motr/hax; \
	 do \
	     install --verbose --directory $$d; \
	 done
	@install --verbose --directory --mode=0775 $(DESTDIR)/var/lib/hare

.PHONY: install-cfgen
install-cfgen: CFGEN_INSTALL_CMD = install
install-cfgen: CFGEN_PIP_CMD = $(PIP) install --ignore-installed --prefix $(DESTDIR)/$(PREFIX) -r $<
install-cfgen: $(CFGEN_EXE) install-cfgen-deps unpack-dhall-bin unpack-dhall-prelude
	@$(call _info,Installing cfgen/dhall configs)
	@install --verbose --directory $(CFGEN_SHARE)
	@for d in cfgen/dhall cfgen/examples; do \
	     $(call _log,copying $$d -> $(CFGEN_SHARE)/$${d##*/}); \
	     cp --no-dereference --preserve=links --recursive $$d $(CFGEN_SHARE); \
	 done

.PHONY: install-cfgen-deps
install-cfgen-deps: cfgen/requirements.txt $(PY_VENV_DIR)
	@$(call _info,Installing cfgen dependencies)
	@$(CFGEN_PIP_CMD)

$(CFGEN_EXE): cfgen/cfgen
	@$(call _info,Installing cfgen)
	@install --verbose --directory $(DESTDIR)/$(PREFIX)/bin
	@$(CFGEN_INSTALL_CMD) --verbose $(TOP_SRC_DIR)cfgen/cfgen $(DESTDIR)/$(PREFIX)/bin

.PHONY: install-systemd
install-systemd: $(wildcard systemd/*)
	@$(call _info,Installing systemd configs)
	@install --verbose --directory $(SYSTEMD_CONFIG_DIR)
	@for f in systemd/*.service; do \
	     $(call _log,copying $$f -> $(SYSTEMD_CONFIG_DIR)); \
	     install --mode=0644 $$f $(SYSTEMD_CONFIG_DIR); \
	 done
	@install --verbose --directory $(CONSUL_LIBEXEC)
	@install --verbose systemd/hare-consul $(CONSUL_LIBEXEC)
	@install --verbose --directory $(CONSUL_SHARE)
	@for f in systemd/consul*.in; do \
	     $(call _log,copying $$f -> $(CONSUL_SHARE)); \
	     install --mode=0644 $$f $(CONSUL_SHARE); \
	 done

.PHONY: install-hax
install-hax: HAX_INSTALL_CMD = $(PIP) install --ignore-installed --prefix $(DESTDIR)/$(PREFIX) $(HAX_WHL:hax/%=%)
install-hax: $(HAX_EXE)

$(HAX_EGG_LINK) $(HAX_EXE): $(HAX_WHL)
	@$(call _info,Installing hax with '$(HAX_INSTALL_CMD)')
	@cd hax && $(HAX_INSTALL_CMD)

.PHONY: install-miniprov
install-miniprov: MP_INSTALL_CMD = $(PIP) install --ignore-installed --prefix $(DESTDIR)/$(PREFIX) $(MP_WHL:provisioning/miniprov/%=%)
install-miniprov: $(MP_EXE)
	@cd provisioning/miniprov && $(SETUP_PY) install

$(MP_EGG_LINK) $(MP_EXE): $(MP_WHL)
	@$(call _info,Installing miniprov with '$(MP_INSTALL_CMD)')
	@cd provisioning/miniprov && $(MP_INSTALL_CMD)

.PHONY: install-vendor
install-vendor:
	@$(call _info,Installing Dhall)
	@install --verbose --directory $(DESTDIR)/$(PREFIX)/bin
	@install --verbose $(wildcard vendor/dhall-bin/current/*) $(DESTDIR)/$(PREFIX)/bin

.PHONY: install-provisioning
install-provisioning:
	@$(call _info,Installing hare provisioning)
	@for f in provisioning/*; do \
	     $(call _log,copying $$f -> $(HARE_CONF)); \
	     install $$f $(HARE_CONF); \
	 done
	@$(call _info,Installing hare provisioning/logrotate)
	@for f in provisioning/logrotate/*; do \
	     $(call _log,copying $$f -> $(HARE_CONF_LOG)); \
	     install $$f $(HARE_CONF_LOG); \
	 done
	@$(call _log,copying provisioning/logrotate/hare -> $(LOGROTATE_CONF_DIR))
	@install --mode=0644 provisioning/logrotate/hare $(LOGROTATE_CONF_DIR)

# devinstall {{{2
.PHONY: devinstall
devinstall: install-dirs devinstall-cfgen devinstall-hax devinstall-miniprov devinstall-systemd devinstall-vendor devinstall-provisioning
	@$(call _info,linking hare utils)
	@for f in utils/*; do \
	     $(call _log,linking $$f -> $(HARE_LIBEXEC)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(HARE_LIBEXEC); \
	 done
	@$(call _info,linking RC rules)
	@for f in rules/*; do \
	     $(call _log,linking $$f -> $(HARE_RULES)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(HARE_RULES); \
	 done
	@$(call _log,linking hctl -> $(DESTDIR)/$(PREFIX)/bin)
	@ln -sf $(TOP_SRC_DIR)hctl $(DESTDIR)/$(PREFIX)/bin
	@$(call _log,linking hctl -> $(DESTDIR)/usr/bin)
	@install --verbose --directory $(DESTDIR)/usr/bin
	@ln -sf $(TOP_SRC_DIR)hctl $(DESTDIR)/usr/bin
	@$(call _log,linking h0q -> $(DESTDIR)/usr/bin)
	@ln -sf $(TOP_SRC_DIR)/utils/h0q $(DESTDIR)/usr/bin
	@$(call _log,creating hare group)
	@groupadd --force hare
	@$(call _log,changing permission of $(DESTDIR)/var/lib/hare)
	@chgrp hare $(DESTDIR)/var/lib/hare
	@chmod --changes g+w $(DESTDIR)/var/lib/hare
	@$(call _log,copying m0trace-prune -> $(ETC_CRON_DIR))
	@install utils/m0trace-prune $(ETC_CRON_DIR)
	@$(call _log,linking virtual environment to $(DESTDIR)/$(PREFIX))
	@ln -s $(PY_VENV_DIR)/lib $(DESTDIR)/$(PREFIX)/lib
	@ln -s $(PY_VENV_DIR)/lib64 $(DESTDIR)/$(PREFIX)/lib64
	@for f in provisioning/miniprov/hare_mp/templates/hare.* \
		  provisioning/setup.yaml ; do \
	     $(call _log,linking $$f -> $(MINIPROV_TMPL_DIR)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(MINIPROV_TMPL_DIR); \
	 done

.PHONY: devinstall-cfgen
devinstall-cfgen: CFGEN_INSTALL_CMD = ln -sf
devinstall-cfgen: CFGEN_PIP_CMD = $(PIP) install --ignore-installed -r $<
devinstall-cfgen: $(CFGEN_EXE) install-cfgen-deps unpack-dhall-bin unpack-dhall-prelude
	@$(call _info,Installing cfgen/dhall configs)
	@install --verbose --directory $(CFGEN_SHARE)
	@for d in cfgen/dhall cfgen/examples; do \
	     $(call _log,linking $$d -> $(CFGEN_SHARE)/$${d##*/}); \
	     ln -sf $(TOP_SRC_DIR)$$d $(CFGEN_SHARE); \
	 done

.PHONY: devinstall-systemd
devinstall-systemd: $(wildcard systemd/*)
	@$(call _info,Installing systemd configs)
	@install --verbose --directory $(SYSTEMD_CONFIG_DIR)
	@for f in systemd/*.service; do \
	     $(call _log,linking $$f -> $(SYSTEMD_CONFIG_DIR)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(SYSTEMD_CONFIG_DIR); \
	 done
	@install --verbose --directory $(CONSUL_LIBEXEC)
	@$(call _log,linking systemd/hare-consul -> $(CONSUL_LIBEXEC))
	@ln -sf $(TOP_SRC_DIR)systemd/hare-consul $(CONSUL_LIBEXEC)
	@install --verbose --directory $(CONSUL_SHARE)
	@for f in systemd/consul*.in; do \
	     $(call _log,linking $$f -> $(CONSUL_SHARE)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(CONSUL_SHARE); \
	 done
	@$(call _info,Reloading systemd configs)
	@systemctl daemon-reload

.PHONY: devinstall-hax
# Don't specify --prefix $(DESTDIR)/$(PREFIX) since we do want to use our
# virtualenv folder instead. Generated executables will point to python binary
# from our virtualenv via shebang. Those executables will be put to /opt/seagate
# as symlinks. So it is critical to have virtualenv folder populated.
devinstall-hax: HAX_INSTALL_CMD = $(SETUP_PY) develop
devinstall-hax: export PYTHONPATH = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages
devinstall-hax: hax/requirements.txt $(HAX_EGG_LINK)
	@$(call _info,Installing hax development dependencies)
	@$(PIP) install --ignore-installed \
					--requirement <(sed -ne '/^#:runtime-requirements:/,$$p' $<)
	@$(call _info,Creating symlinks for hax executables)
	@ln -v -sf $(PY_VENV_DIR)/bin/hax $(DESTDIR)/$(PREFIX)/bin
	@ln -v -sf $(PY_VENV_DIR)/bin/q $(DESTDIR)/$(PREFIX)/bin

.PHONY: devinstall-miniprov
devinstall-miniprov: MP_INSTALL_CMD = $(SETUP_PY) develop
devinstall-miniprov: export PYTHONPATH = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages
devinstall-miniprov: provisioning/miniprov/requirements.txt $(MP_EGG_LINK)
	@$(call _info,Installing miniprov development dependencies)
	@$(PIP) install --ignore-installed \
					--requirement <(sed -ne '/^#:runtime-requirements:/,$$p' $<)
	@$(call _info,Creating symlinks for mini-provisioner executables)
	@ln -v -sf $(PY_VENV_DIR)/bin/hare_setup $(DESTDIR)/$(PREFIX)/bin

.PHONY: devinstall-vendor
devinstall-vendor:
	@$(call _info,Installing Dhall)
	@install --verbose --directory $(DESTDIR)/$(PREFIX)/bin
	@ln -v -sf $(addprefix $(TOP_SRC_DIR), $(wildcard vendor/dhall-bin/current/*)) $(DESTDIR)/$(PREFIX)/bin

.PHONY: devinstall-provisioning
devinstall-provisioning:
	@$(call _info,Installing hare provisioning)
	@for f in provisioning/*; do \
	     $(call _log,copying $$f -> $(HARE_CONF)); \
	     install $$f $(HARE_CONF); \
	 done
	@$(call _info,Installing hare provisioning/logrotate)
	@for f in provisioning/logrotate/*; do \
	     $(call _log,copying $$f -> $(HARE_CONF_LOG)); \
	     install $$f $(HARE_CONF_LOG); \
	 done

# Uninstall ------------------------------------------- {{{1
#

HAX_EGG        = $(wildcard $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hax-*.egg)
HAX_MODULE     = $(wildcard $(DESTDIR)/$(PREFIX)/lib64/python3.$(PY3_VERSION_MINOR)/site-packages/*hax*)
EASY_INST_PTH  = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/easy-install.pth

.PHONY: uninstall
uninstall:
	@$(call _info,Un-installing)
	@for d in $(CFGEN_EXE) $(CFGEN_SHARE) \
	          $(HARE_CONF) \
	          $(HARE_RULES) \
	          $(HAX_EXE) $(HAX_EGG_LINK) $(HAX_EGG) $(HAX_MODULE) \
	          $(EASY_INST_PTH) \
	          $(CONSUL_LIBEXEC) $(CONSUL_SHARE) \
	          $(SYSTEMD_CONFIG_DIR)/hare*.service \
	          $(DESTDIR)/$(PREFIX) \
	          $(DESTDIR)/usr/bin/hctl \
	          $(DESTDIR)/var/lib/hare \
	          $(DESTDIR)/var/log/seagate/hare \
	          $(DESTDIR)/var/motr/hax; \
	 do \
	     if [[ -e $$d ]]; then \
	         $(call _log,removing $$d); \
	         rm -rf $$d; \
	     fi; \
	 done

# Linters --------------------------------------------- {{{1
#

PYTHON_SCRIPTS := $(shell grep 'python3' -n utils/* 2>/dev/null | grep ':1:' | sed 's/^\([^:]*\):.*$$/\1/g')

.PHONY: check
check: check-cfgen check-hax check-miniprov flake8 mypy

.PHONY: check-cfgen
check-cfgen: $(PY_VENV_DIR)
	@$(call _info,Checking cfgen)
	@$(PY_VENV); $(MAKE) --quiet -C cfgen flake8 typecheck

.PHONY: test-hax
test-hax: $(PY_VENV_DIR)
	@$(call _info,Running hax autotests)
	@cd hax &&\
	  $(PY_VENV) &&\
	  pytest -v test/

.PHONY: lint-hax
lint-hax: $(PY_VENV_DIR)
	@cd hax &&\
	  $(PY_VENV) &&\
	  MYPYPATH=../stubs $(PYTHON) setup.py flake8 mypy

.PHONY: check-hax
check-hax: $(PY_VENV_DIR) lint-hax test-hax

.PHONY: check-miniprov
check-miniprov:
	@$(call _info,Checking hare_mp)
	@$(MAKE) --quiet -C provisioning/miniprov check

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	@$(call _info,Checking files with flake8)
	@$(PY_VENV); flake8 $(FLAKE8_OPTS) $^

.PHONY: mypy
override MYPY_OPTS := --config-file hax/mypy.ini $(MYPY_OPTS)
mypy: $(PYTHON_SCRIPTS)
	@$(call _info,Checking files with mypy)
	@$(PY_VENV); \
          set -eu -o pipefail; for f in $^; do MYPYPATH=stubs:hax:utils mypy $(MYPY_OPTS) $$f; done

# Tests ----------------------------------------------- {{{1
#

.PHONY: test
test: test-cfgen

.PHONY: test-cfgen
test-cfgen: $(PY_VENV_DIR) unpack-dhall-bin unpack-dhall-prelude
	@$(call _info,Testing cfgen)
	@$(PY_VENV); PATH=$$PWD/vendor/dhall-bin/current:$$PATH \
		$(MAKE) --quiet -C cfgen test-cfgen check-dhall

# RPM ------------------------------------------------- {{{1
#

VERSION   := $(shell cat VERSION)
GITREV     = git$(shell git rev-parse --short HEAD)
DIST_FILE := cortx-hare-$(VERSION).tar.gz

RPMBUILD_DIR    := $(HOME)/rpmbuild
RPMBUILD_TOPDIR := $(abspath $(RPMBUILD_DIR))
RPMSOURCES_DIR  := $(RPMBUILD_DIR)/SOURCES
RPMSPECS_DIR    := $(RPMBUILD_DIR)/SPECS

.PHONY: dist
dist: unpack-dhall-bin unpack-dhall-prelude
	@$(call _info,Generating dist archive)
	@rm -f $(DIST_FILE)
	@git archive -v --prefix=cortx-hare/ HEAD -o $(DIST_FILE:.gz=)
	@tar --append --verbose --transform 's#^vendor#cortx-hare/vendor#' \
	     --file=$(DIST_FILE:.gz=) vendor
	@gzip $(DIST_FILE:.gz=)

.PHONY: __rpm_pre
__rpm_pre: dist
	@$(call _info,Preparing rpmbuild environment)
	@mkdir -v -p $(RPMSOURCES_DIR) $(RPMSPECS_DIR)
	@mv -v $(DIST_FILE) $(RPMSOURCES_DIR)
	@cp -v hare.spec $(RPMSPECS_DIR)
	@chown $$(id -u):$$(id -g) $(RPMSOURCES_DIR)/$(DIST_FILE)
	@chown $$(id -u):$$(id -g) $(RPMSPECS_DIR)/hare.spec

.PHONY: __rpm
__rpm:
	@$(call _info,Building rpm packages)
	@rpmbuild -ba $(RPMSPECS_DIR)/hare.spec \
	          --define "_topdir $(RPMBUILD_TOPDIR)" \
	          --define "h_version $(VERSION)" \
	          --define "h_gitrev $(GITREV)" \
	          $(RPMBUILD_FLAGS)

.PHONY: __rpm_post
__rpm_post:
	@rm -f $(RPMSOURCES_DIR)/$(DIST_FILE) $(RPMSPECS_DIR)/hare.spec

.PHONY: __rpm_srpm
__rpm_srpm:
	@$(call _info,Building source rpm packages)
	@rpmbuild -bs $(RPMSPECS_DIR)/hare.spec \
	          --define "_topdir $(RPMBUILD_TOPDIR)" \
	          --define "h_version $(VERSION)" \
	          --define "h_gitrev $(GITREV)" \
	          $(RPMBUILD_FLAGS)

.PHONY: rpm
rpm:
	@$(MAKE) __rpm_pre
	@$(MAKE) __rpm
	@$(MAKE) __rpm_post

.PHONY: srpm
srpm:
	@$(MAKE) __rpm_pre
	@$(MAKE) __rpm_srpm
	@$(MAKE) __rpm_post

# Docker ---------------------------------------------- {{{1
#

# delegate all 'docker*' targets to docker/Makefile
docker-%:
	@$(MAKE) -C docker/ $*

# Functions ------------------------------------------- {{{1
#

# all variations of white and grey colors are invisible on terminals that use
# Solarized colorscheme, cyan seems to be a good compromise here, it looks
# decent on the default black/white terminal, as well as on Solarized
define _info
    if [[ -t 1 ]]; then \
        CYAN=$$(tput bold; tput setaf 6); \
        NC=$$(tput sgr0); \
    fi; \
    echo "$${CYAN}--> $(1)$${NC}"
endef

define _log
    if [[ -t 1 ]]; then \
        YELLOW=$$(tput setaf 3); \
        NC=$$(tput sgr0); \
    fi; \
    echo "$${YELLOW}    $(1)$${NC}"
endef

# vim: textwidth=80 nowrap foldmethod=marker
