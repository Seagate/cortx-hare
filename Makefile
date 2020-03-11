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

# Build ----------------------------------------------- {{{1
#

.PHONY: build
build: hax
	@$(MAKE) --quiet check

.PHONY: hax
HAX_VERSION := $(shell cat VERSION)
HAX_WHL     := hax/dist/hax-$(HAX_VERSION)-cp$(PY3_VERSION)-cp$(PY3_VERSION)m-linux_x86_64.whl
hax: $(HAX_WHL)

HAX_SRC := $(wildcard hax/setup.py hax/hax/*.py hax/hax/*.[ch])
$(HAX_WHL): $(PY_VENV_DIR) $(HAX_SRC)
	@$(call _info,Building hax .whl package)
	@cd hax && $(SETUP_PY) bdist_wheel

$(PY_VENV_DIR): $(patsubst %,%/requirements.txt,cfgen hax)
	@$(call _info,Initializing virtual env in $(PY_VENV_DIR))
	@$(PYTHON) -m venv $@
	@$(call _info,Installing pip modules in virtual env)
	@for f in $^; do \
	     $(call _log,processing $$f); \
	     $(PIP) install -r $$f; \
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

.PHONY: clean
clean: clean-hax clean-mypy clean-dhall-prelude

.PHONY: clean-hax
clean-hax:
	@$(call _info,Cleaning hax)
	@for d in hax/build hax/dist hax/hax.egg-info hax/*.so \
	          hax/hax/__pycache__; do \
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

# Install --------------------------------------------- {{{1
#

PREFIX            := opt/seagate/eos/hare
CFGEN_EXE          = $(DESTDIR)/$(PREFIX)/bin/cfgen
CFGEN_SHARE        = $(DESTDIR)/$(PREFIX)/share/cfgen
CONSUL_LIBEXEC     = $(DESTDIR)/$(PREFIX)/libexec/consul
CONSUL_SHARE       = $(DESTDIR)/$(PREFIX)/share/consul
HARE_CONF          = $(DESTDIR)/$(PREFIX)/conf
HARE_LIBEXEC       = $(DESTDIR)/$(PREFIX)/libexec
HARE_PACEMAKER     = $(DESTDIR)/$(PREFIX)/pacemaker
HAX_EXE            = $(DESTDIR)/$(PREFIX)/bin/hax
HAX_EGG_LINK       = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hax.egg-link
SYSTEMD_CONFIG_DIR = $(DESTDIR)/usr/lib/systemd/system

# install {{{2
.PHONY: install
install: install-dirs install-cfgen install-hax install-systemd install-vendor
	@$(call _info,Installing hare utils)
	@for f in utils/*; do \
	     $(call _log,copying $$f -> $(HARE_LIBEXEC)); \
	     install $$f $(HARE_LIBEXEC); \
	 done
	@$(call _info,Installing pacemaker scripts)
	@for f in pacemaker/*; do \
	     $(call _log,copying $$f -> $(HARE_PACEMAKER)); \
	     install $$f $(HARE_PACEMAKER); \
	 done
	@$(call _info,Installing hare provisioning)
	@for f in provisioning/*; do \
	     $(call _log,copying $$f -> $(HARE_CONF)); \
	     install $$f $(HARE_CONF); \
	 done
	@$(call _log,copying hctl -> $(DESTDIR)/$(PREFIX)/bin)
	@install hctl $(DESTDIR)/$(PREFIX)/bin
	@$(call _log,linking hctl -> $(DESTDIR)/usr/bin)
	@install --verbose --directory $(DESTDIR)/usr/bin
	@ln -sf /$(PREFIX)/bin/hctl $(DESTDIR)/usr/bin

.PHONY: install-dirs
install-dirs:
	@for d in $(HARE_CONF) \
                  $(HARE_LIBEXEC) \
                  $(HARE_PACEMAKER) \
	          $(DESTDIR)/var/log/hare \
	          $(DESTDIR)/var/mero/hax; \
	 do \
	     install --verbose --directory $$d; \
	 done
	@install --verbose --directory --mode=0775 $(DESTDIR)/var/lib/hare

.PHONY: unpack-dhall-prelude
unpack-dhall-prelude:
	$(MAKE) --quiet -C cfgen unpack-dhall-prelude

.PHONY: install-cfgen
install-cfgen: CFGEN_INSTALL_CMD = install
install-cfgen: $(CFGEN_EXE) install-cfgen-deps unpack-dhall-prelude
	@$(call _info,Installing cfgen/dhall configs)
	@install --verbose --directory $(CFGEN_SHARE)
	@for d in cfgen/dhall cfgen/examples; do \
	     $(call _log,copying $$d -> $(CFGEN_SHARE)/$${d##*/}); \
	     cp --no-dereference --preserve=links --recursive $$d $(CFGEN_SHARE); \
	 done

.PHONY: install-cfgen-deps
install-cfgen-deps: cfgen/requirements.txt $(PY_VENV_DIR)
	@$(call _info,Installing cfgen dependencies)
	@$(PIP) install --ignore-installed --prefix $(DESTDIR)/$(PREFIX) -r $<

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

.PHONY: install-vendor
install-vendor: vendor/consul-bin/current/consul \
                $(wildcard vendor/dhall-bin/current/*)
	@$(call _info,Installing Consul and Dhall)
	@install --verbose --directory $(DESTDIR)/$(PREFIX)/bin
	@install --verbose $^ $(DESTDIR)/$(PREFIX)/bin

# devinstall {{{2
.PHONY: devinstall
devinstall: install-dirs devinstall-cfgen devinstall-hax devinstall-systemd devinstall-vendor
	@$(call _info,linking hare utils)
	@for f in utils/*; do \
	     $(call _log,linking $$f -> $(HARE_LIBEXEC)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(HARE_LIBEXEC); \
	 done
	@$(call _info,linking pacemaker scripts)
	@for f in pacemaker/*; do \
	     $(call _log,linking $$f -> $(HARE_PACEMAKER)); \
	     ln -sf $(TOP_SRC_DIR)$$f $(HARE_PACEMAKER); \
	 done
	@$(call _log,linking hctl -> $(DESTDIR)/$(PREFIX)/bin)
	@ln -sf $(TOP_SRC_DIR)hctl $(DESTDIR)/$(PREFIX)/bin
	@$(call _log,linking hctl -> $(DESTDIR)/usr/bin)
	@install --verbose --directory $(DESTDIR)/usr/bin
	@ln -sf $(TOP_SRC_DIR)hctl $(DESTDIR)/usr/bin
	@$(call _log,creating hare group)
	@groupadd --force hare
	@$(call _log,changing permission of $(DESTDIR)/var/lib/hare)
	@chgrp hare $(DESTDIR)/var/lib/hare 
	@chmod --changes g+w $(DESTDIR)/var/lib/hare


.PHONY: devinstall-cfgen
devinstall-cfgen: CFGEN_INSTALL_CMD = ln -sf
devinstall-cfgen: $(CFGEN_EXE) install-cfgen-deps unpack-dhall-prelude
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
devinstall-hax: HAX_INSTALL_CMD = $(SETUP_PY) develop --prefix $(DESTDIR)/$(PREFIX)
devinstall-hax: export PYTHONPATH = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages
devinstall-hax: $(HAX_EGG_LINK)

.PHONY: devinstall-vendor
devinstall-vendor: vendor/consul-bin/current/consul \
                   $(wildcard vendor/dhall-bin/current/*)
	@$(call _info,Installing Consul and Dhall)
	@install --verbose --directory $(DESTDIR)/$(PREFIX)/bin
	@ln -v -sf $(addprefix $(TOP_SRC_DIR), $^) $(DESTDIR)/$(PREFIX)/bin

# Uninstall ------------------------------------------- {{{1
#

HAX_EGG       = $(wildcard $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hax-*.egg)
HAX_MODULE    = $(wildcard $(DESTDIR)/$(PREFIX)/lib64/python3.$(PY3_VERSION_MINOR)/site-packages/*hax*)
EASY_INST_PTH = $(DESTDIR)/$(PREFIX)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/easy-install.pth

.PHONY: uninstall
uninstall:
	@$(call _info,Un-installing)
	@for d in $(CFGEN_EXE) $(CFGEN_SHARE) \
	          $(HARE_CONF) \
	          $(HAX_EXE) $(HAX_EGG_LINK) $(HAX_EGG) $(HAX_MODULE) \
	          $(EASY_INST_PTH) \
	          $(CONSUL_LIBEXEC) $(CONSUL_SHARE) \
	          $(SYSTEMD_CONFIG_DIR)/hare*.service \
	          $(DESTDIR)/$(PREFIX) \
	          $(DESTDIR)/usr/bin/hctl \
	          $(DESTDIR)/var/lib/hare \
	          $(DESTDIR)/var/log/hare \
	          $(DESTDIR)/var/mero/hax; \
	 do \
	     if [[ -e $$d ]]; then \
	         $(call _log,removing $$d); \
	         rm -rf $$d; \
	     fi; \
	 done

# Linters --------------------------------------------- {{{1
#

PYTHON_SCRIPTS := utils/hare-shutdown utils/hare-status

.PHONY: check
check: check-cfgen check-hax flake8 mypy

.PHONY: check-cfgen
check-cfgen: $(PY_VENV_DIR)
	@$(call _info,Checking cfgen)
	@$(PY_VENV); $(MAKE) --quiet -C cfgen flake8 typecheck

.PHONY: check-hax
check-hax: $(PY_VENV_DIR)
	@$(call _info,Checking hax)
	@cd hax &&\
	  $(PY_VENV) &&\
	  MYPYPATH=../stubs $(PYTHON) setup.py flake8 mypy

.PHONY: flake8
flake8: $(PYTHON_SCRIPTS)
	@$(call _info,Checking files with flake8)
	@$(PY_VENV); flake8 $(FLAKE8_OPTS) $^

.PHONY: mypy
override MYPY_OPTS := --config-file hax/mypy.ini $(MYPY_OPTS)
mypy: $(PYTHON_SCRIPTS)
	@$(call _info,Checking files with mypy)
	@$(PY_VENV); \
	 set -eu -o pipefail; for f in $^; do MYPYPATH=stubs mypy $(MYPY_OPTS) $$f; done

# Tests ----------------------------------------------- {{{1
#

.PHONY: test
test: test-cfgen

.PHONY: test-cfgen
test-cfgen: $(PY_VENV_DIR)
	@$(call _info,Testing cfgen)
	@$(PY_VENV); $(MAKE) --quiet -C cfgen test-cfgen check-dhall

# RPM ------------------------------------------------- {{{1
#

VERSION   := $(shell cat VERSION)
GITREV     = git$(shell git rev-parse --short HEAD)
DIST_FILE := eos-hare-$(VERSION).tar.gz

RPMBUILD_DIR    := $(HOME)/rpmbuild
RPMBUILD_TOPDIR := $(abspath $(RPMBUILD_DIR))
RPMSOURCES_DIR  := $(RPMBUILD_DIR)/SOURCES
RPMSPECS_DIR    := $(RPMBUILD_DIR)/SPECS

.PHONY: dist
dist:
	@$(call _info,Generating dist archive)
	@rm -f $(DIST_FILE)
	@git archive -v --prefix=eos-hare/ HEAD -o $(DIST_FILE:.gz=)
	git submodule foreach --recursive \
	     "git archive --prefix=eos-hare/\$$path/ --output=\$$sha1.tar HEAD \
	      && tar --concatenate --file=$$(pwd)/$(DIST_FILE:.gz=) \$$sha1.tar \
	      && rm \$$sha1.tar"
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
	@$(MAKE) --quiet __rpm_pre
	@$(MAKE) --quiet __rpm
	@$(MAKE) --quiet __rpm_post

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
