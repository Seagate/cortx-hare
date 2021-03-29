.PHONY: default
default: build

.PHONY: help
help:
	@echo 'General targets:'
	@echo '  build   - build binary components (miniprov)'
	@echo '  test    - run tests'
	@echo '  clean   - remove build artefacts'
	@echo '  install - system-wide installation, respects DESTDIR'
	@echo
	@echo 'Code linters:'
	@echo '  check   - run `flake8` and `mypy` linters for Python code'
	@echo '  flake8  - run `flake8` for Python code'
	@echo '  mypy    - run `mypy` for Python code'

# Globals --------------------------------------------- {{{1
#

SHELL := bash

TOP_SRC_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PY_VENV_DIR := $(TOP_SRC_DIR)/../../.py3venv
PYTHON      := python3.6
PY_VENV     := source $(PY_VENV_DIR)/bin/activate
PIP         := $(PY_VENV); pip3
SETUP_PY    := $(PY_VENV); $(PYTHON) setup.py
PY3_VERSION := 36
PY3_VERSION_MINOR := $(shell grep -o . <<<$(PY3_VERSION) | tail -n1)

# Build ----------------------------------------------- {{{1
#

.PHONY: build
build: miniprov
	@$(MAKE) --quiet check

.PHONY: miniprov
MP_VERSION := $(shell cat ../../VERSION)
MP_WHL := dist/hare_mp-$(MP_VERSION)-py3-none-any.whl
miniprov: $(MP_WHL)

MP_SRC := $(shell find hare_mp/ -type f -name '*.py')
$(MP_WHL): $(PY_VENV_DIR) $(MP_SRC)
	@$(call _info,Building miniprov .whl package)
	@$(SETUP_PY) bdist_wheel

$(PY_VENV_DIR): requirements.txt
	@$(call _info,Initializing virtual env in $(PY_VENV_DIR))
	@$(PYTHON) -m venv --system-site-packages $@
	@$(call _info,Installing pip modules in virtual env)
	@$(PIP) install --ignore-installed -r ./requirements.txt

# Install ----------------------------------------------- {{{1
#

MP_EXE        = $(DESTDIR)/bin/hare_setup
MP_EGG_LINK   = $(DESTDIR)/lib/python3.$(PY3_VERSION_MINOR)/site-packages/hare_mp.egg-link


.PHONY: install-miniprov-deps
install-miniprov-deps: requirements.txt $(PY_VENV_DIR)
	@$(call _info,Installing miniprov dependencies)
	@$(PIP) install --ignore-installed --prefix $(DESTDIR) -r $<

.PHONY: install
install: MP_INSTALL_CMD = $(PIP) install --ignore-installed --prefix $(DESTDIR) $(MP_WHL:hare_mp/%=%)
install: install-miniprov-deps $(MP_EXE)

$(MP_EGG_LINK) $(MP_EXE): $(MP_WHL)
	@$(call _info,Installing miniprov with '$(MP_INSTALL_CMD)')
	@$(MP_INSTALL_CMD)

# Clean ----------------------------------------------- {{{1
#

.PHONY: clean
clean:
	@$(call _info,Cleaning miniprov)
	@rm -rvf {build,dist,hare_mp.egg-info}
	@find ./ -name '__pycache__' | while read d; do \
	     if [[ -e $$d ]]; then \
	         $(call _log,removing $$d); \
	         rm -rf $$d; \
	     fi; \
	 done

# Linters --------------------------------------------- {{{1
#

.PHONY: check
check: flake8 mypy

.PHONY: test
test: $(PY_VENV_DIR) $(MP_SRC)
	@$(SETUP_PY) test

.PHONY: flake8
flake8:
	@$(call _info,Checking files with flake8)
	@$(PY_VENV); flake8 hare_mp

.PHONY: mypy
mypy:
	@$(call _info,Checking files with mypy)
	@$(PY_VENV); \
	 set -eu -o pipefail; MYPYPATH=../../stubs mypy $(MYPY_OPTS) hare_mp

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
