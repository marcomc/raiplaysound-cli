SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

INSTALL_NAME ?= raiplaysound-cli
INSTALL_DIR ?= $(HOME)/.local/share/raiplaysound-cli
INSTALL_VENV ?= $(INSTALL_DIR)/venv
INSTALL_PIP := $(INSTALL_VENV)/bin/pip
INSTALL_LAUNCHER_DIR ?= $(INSTALL_DIR)/bin
INSTALL_LAUNCHER_PATH ?= $(INSTALL_LAUNCHER_DIR)/$(INSTALL_NAME)

LAUNCHER_DIR ?= launcher
LAUNCHER_SCRIPT := $(LAUNCHER_DIR)/$(INSTALL_NAME)
LAUNCHER_SUPPORT := $(LAUNCHER_DIR)/launcher_support.py

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
INSTALL_PATH ?= $(BINDIR)/$(INSTALL_NAME)

MARKDOWNLINT ?= markdownlint
DOCS := README.md AGENTS.md TODO.md CHANGELOG.md docs/*.md

.PHONY: help check-deps venv dev-deps _install-venv install install-dev uninstall uninstall-dev reinstall test lint lint-docs format run clean

help:
	@echo "Targets:"
	@echo "  make install     # Standalone install under $(INSTALL_DIR) with symlink at $(INSTALL_PATH)"
	@echo "  make install-dev # Editable dev install with symlink at $(INSTALL_PATH)"
	@echo "  make uninstall   # Remove standalone install and symlink"
	@echo "  make uninstall-dev # Remove dev symlink and restore standalone install if present"
	@echo "  make reinstall   # Reinstall the standalone tool"
	@echo "  make venv        # Create project virtualenv"
	@echo "  make test        # Run unit tests"
	@echo "  make lint        # Run Python lint, typing, format check, tests, compile, markdownlint"
	@echo "  make lint-docs   # Run markdownlint"
	@echo "  make format      # Format Python code with black"
	@echo "  make run         # Show installed CLI help"
	@echo "  make clean       # Remove build/test artifacts"

check-deps:
	@echo "Checking prerequisites..."
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { echo "python not found: $(PYTHON)"; exit 1; }
	@"$(PYTHON)" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
		|| { echo "Python 3.10+ required (found $$($(PYTHON) --version 2>&1))"; exit 1; }
	@echo "Using $$($(PYTHON) --version 2>&1)"
	@mkdir -p "$(BINDIR)"
	@if echo "$$PATH" | tr ':' '\n' | grep -Fxq "$(BINDIR)"; then \
		echo "$(BINDIR) is on PATH"; \
	else \
		echo "warning: $(BINDIR) is not on PATH"; \
		echo "add this to your shell profile:"; \
		echo "export PATH=\"$(BINDIR):\$$PATH\""; \
	fi

venv:
	@if ! "$(VENV_PIP)" --version >/dev/null 2>&1; then \
		rm -rf "$(VENV)"; \
		"$(PYTHON)" -m venv "$(VENV)"; \
		"$(VENV_PIP)" install --upgrade pip --quiet; \
	fi

dev-deps: venv
	@"$(VENV_PIP)" install -e ".[dev]" --quiet

_install-venv:
	@if ! "$(INSTALL_PIP)" --version >/dev/null 2>&1; then \
		rm -rf "$(INSTALL_VENV)"; \
		mkdir -p "$(INSTALL_DIR)"; \
		"$(PYTHON)" -m venv "$(INSTALL_VENV)"; \
	fi
	@"$(INSTALL_PIP)" install --upgrade pip setuptools wheel --quiet

install: check-deps _install-venv
	@"$(INSTALL_PIP)" install --no-build-isolation . --quiet
	@mkdir -p "$(BINDIR)"
	@mkdir -p "$(INSTALL_LAUNCHER_DIR)"
	@install -m 755 "$(LAUNCHER_SCRIPT)" "$(INSTALL_LAUNCHER_PATH)"
	@install -m 644 "$(LAUNCHER_SUPPORT)" "$(INSTALL_LAUNCHER_DIR)/launcher_support.py"
	@ln -sf "$(INSTALL_LAUNCHER_PATH)" "$(INSTALL_PATH)"
	@echo "Installed standalone CLI at $(INSTALL_PATH)"

install-dev: check-deps dev-deps
	@mkdir -p "$(BINDIR)"
	@ln -sf "$(CURDIR)/$(LAUNCHER_SCRIPT)" "$(INSTALL_PATH)"
	@echo "Installed editable dev CLI at $(INSTALL_PATH)"

uninstall:
	@rm -f "$(INSTALL_PATH)"
	@rm -rf "$(INSTALL_DIR)"
	@echo "Removed $(INSTALL_PATH)"
	@echo "Removed $(INSTALL_DIR)"

uninstall-dev:
	@if [ -L "$(INSTALL_PATH)" ] && [ "$$(readlink "$(INSTALL_PATH)")" = "$(CURDIR)/$(LAUNCHER_SCRIPT)" ]; then \
		rm -f "$(INSTALL_PATH)"; \
		echo "Removed dev symlink $(INSTALL_PATH)"; \
		if [ -x "$(INSTALL_LAUNCHER_PATH)" ]; then \
			ln -sf "$(INSTALL_LAUNCHER_PATH)" "$(INSTALL_PATH)"; \
			echo "Restored standalone install at $(INSTALL_PATH)"; \
		elif [ -x "$(INSTALL_VENV)/bin/$(INSTALL_NAME)" ]; then \
			ln -sf "$(INSTALL_VENV)/bin/$(INSTALL_NAME)" "$(INSTALL_PATH)"; \
			echo "Restored legacy standalone install at $(INSTALL_PATH)"; \
		else \
			echo "No standalone install found"; \
		fi; \
	else \
		echo "$(INSTALL_PATH) is not the dev symlink"; \
	fi

reinstall: uninstall install

test: dev-deps
	@PYTHONPATH=src "$(VENV_PYTHON)" -m pytest -q

lint: test lint-docs
	@"$(VENV)/bin/ruff" check src tests
	@"$(VENV)/bin/mypy" src tests
	@"$(VENV)/bin/black" --check src tests
	@"$(VENV_PYTHON)" -m py_compile src/raiplaysound_cli/*.py launcher/*.py launcher/raiplaysound-cli

lint-docs:
	@$(MARKDOWNLINT) $(DOCS) --config /Users/mmassari/.markdownlint.json

format: dev-deps
	@"$(VENV)/bin/black" src tests

run:
	@"$(INSTALL_PATH)" --help

clean:
	@rm -rf "$(VENV)" .pytest_cache .coverage __pycache__ src/*.egg-info dist build
	@echo "Removed development artifacts"
	@echo "Standalone install at $(INSTALL_PATH) was left unchanged"
