SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

INSTALL_NAME ?= raiplaysound-cli
DAILY_SYNC_NAME ?= raiplaysound-cli-daily-sync
INSTALL_DIR ?= $(HOME)/.local/share/raiplaysound-cli
INSTALL_VENV ?= $(INSTALL_DIR)/venv
INSTALL_PIP := $(INSTALL_VENV)/bin/pip
INSTALL_LAUNCHER_DIR ?= $(INSTALL_DIR)/bin
INSTALL_LAUNCHER_PATH ?= $(INSTALL_LAUNCHER_DIR)/$(INSTALL_NAME)
INSTALL_DAILY_SYNC_PATH ?= $(INSTALL_LAUNCHER_DIR)/$(DAILY_SYNC_NAME)

LAUNCHER_DIR ?= launcher
LAUNCHER_SCRIPT := $(LAUNCHER_DIR)/$(INSTALL_NAME)
DAILY_SYNC_SCRIPT := $(LAUNCHER_DIR)/$(DAILY_SYNC_NAME)
LAUNCHER_SUPPORT := $(LAUNCHER_DIR)/launcher_support.py
DEV_LAUNCHER_PATH ?= $(VENV)/bin/$(INSTALL_NAME)
DEV_DAILY_SYNC_PATH ?= $(VENV)/bin/$(DAILY_SYNC_NAME)
DEV_LAUNCHER_SUPPORT_PATH ?= $(VENV)/bin/launcher_support.py
INSTALL_VENV_PYTHON_ABS := $(abspath $(INSTALL_VENV)/bin/python)
INSTALL_LAUNCHER_PATH_ABS := $(abspath $(INSTALL_LAUNCHER_PATH))
INSTALL_DAILY_SYNC_PATH_ABS := $(abspath $(INSTALL_DAILY_SYNC_PATH))
DEV_VENV_PYTHON_ABS := $(abspath $(VENV_PYTHON))
DEV_LAUNCHER_PATH_ABS := $(abspath $(DEV_LAUNCHER_PATH))
DEV_DAILY_SYNC_PATH_ABS := $(abspath $(DEV_DAILY_SYNC_PATH))

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
INSTALL_PATH ?= $(BINDIR)/$(INSTALL_NAME)
DAILY_SYNC_INSTALL_PATH ?= $(BINDIR)/$(DAILY_SYNC_NAME)

LAUNCHAGENT_TEMPLATE ?= launchagent/com.raiplaysound-cli.daily-sync.plist
LAUNCHAGENT_LABEL ?= com.raiplaysound-cli.daily-sync
LAUNCHAGENT_DEST ?= $(HOME)/Library/LaunchAgents/$(LAUNCHAGENT_LABEL).plist

MARKDOWNLINT ?= markdownlint
DOCS := README.md AGENTS.md TODO.md CHANGELOG.md docs/*.md

.PHONY: help check-deps venv dev-deps _install-venv install install-dev uninstall uninstall-dev reinstall launchagent-install launchagent-uninstall test lint lint-docs format run clean

help:
	@echo "Targets:"
	@echo "  make install     # Standalone install under $(INSTALL_DIR) with symlink at $(INSTALL_PATH)"
	@echo "  make install-dev # Editable dev install with symlink at $(INSTALL_PATH)"
	@echo "  make uninstall   # Remove standalone install and symlink"
	@echo "  make uninstall-dev # Remove dev symlink and restore standalone install if present"
	@echo "  make launchagent-install # Install and load daily favourites sync at 08:00"
	@echo "  make launchagent-uninstall # Unload and remove daily favourites sync"
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
	@{ printf '#!%s\n' "$(INSTALL_VENV_PYTHON_ABS)"; tail -n +2 "$(LAUNCHER_SCRIPT)"; } > "$(INSTALL_LAUNCHER_PATH)"
	@{ printf '#!%s\n' "$(INSTALL_VENV_PYTHON_ABS)"; tail -n +2 "$(DAILY_SYNC_SCRIPT)"; } > "$(INSTALL_DAILY_SYNC_PATH)"
	@install -m 644 "$(LAUNCHER_SUPPORT)" "$(INSTALL_LAUNCHER_DIR)/launcher_support.py"
	@chmod 755 "$(INSTALL_LAUNCHER_PATH)"
	@chmod 755 "$(INSTALL_DAILY_SYNC_PATH)"
	@ln -sf "$(INSTALL_LAUNCHER_PATH_ABS)" "$(INSTALL_PATH)"
	@ln -sf "$(INSTALL_DAILY_SYNC_PATH_ABS)" "$(DAILY_SYNC_INSTALL_PATH)"
	@echo "Installed standalone CLI at $(INSTALL_PATH)"
	@echo "Installed daily sync companion at $(DAILY_SYNC_INSTALL_PATH)"

install-dev: check-deps dev-deps
	@mkdir -p "$(BINDIR)"
	@{ printf '#!%s\n' "$(DEV_VENV_PYTHON_ABS)"; tail -n +2 "$(LAUNCHER_SCRIPT)"; } > "$(DEV_LAUNCHER_PATH)"
	@{ printf '#!%s\n' "$(DEV_VENV_PYTHON_ABS)"; tail -n +2 "$(DAILY_SYNC_SCRIPT)"; } > "$(DEV_DAILY_SYNC_PATH)"
	@install -m 644 "$(LAUNCHER_SUPPORT)" "$(DEV_LAUNCHER_SUPPORT_PATH)"
	@chmod 755 "$(DEV_LAUNCHER_PATH)"
	@chmod 755 "$(DEV_DAILY_SYNC_PATH)"
	@ln -sf "$(DEV_LAUNCHER_PATH_ABS)" "$(INSTALL_PATH)"
	@ln -sf "$(DEV_DAILY_SYNC_PATH_ABS)" "$(DAILY_SYNC_INSTALL_PATH)"
	@echo "Installed editable dev CLI at $(INSTALL_PATH)"
	@echo "Installed editable daily sync companion at $(DAILY_SYNC_INSTALL_PATH)"

uninstall:
	@rm -f "$(INSTALL_PATH)"
	@rm -f "$(DAILY_SYNC_INSTALL_PATH)"
	@rm -rf "$(INSTALL_DIR)"
	@echo "Removed $(INSTALL_PATH)"
	@echo "Removed $(DAILY_SYNC_INSTALL_PATH)"
	@echo "Removed $(INSTALL_DIR)"

uninstall-dev:
	@if [ -L "$(INSTALL_PATH)" ] && [ "$$(readlink "$(INSTALL_PATH)")" = "$(DEV_LAUNCHER_PATH_ABS)" ]; then \
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
	@if [ -L "$(DAILY_SYNC_INSTALL_PATH)" ] && [ "$$(readlink "$(DAILY_SYNC_INSTALL_PATH)")" = "$(DEV_DAILY_SYNC_PATH_ABS)" ]; then \
		rm -f "$(DAILY_SYNC_INSTALL_PATH)"; \
		echo "Removed dev symlink $(DAILY_SYNC_INSTALL_PATH)"; \
		if [ -x "$(INSTALL_DAILY_SYNC_PATH)" ]; then \
			ln -sf "$(INSTALL_DAILY_SYNC_PATH)" "$(DAILY_SYNC_INSTALL_PATH)"; \
			echo "Restored standalone daily sync at $(DAILY_SYNC_INSTALL_PATH)"; \
		else \
			echo "No standalone daily sync companion found"; \
		fi; \
	fi

reinstall: uninstall install

launchagent-install: install
	@mkdir -p "$(HOME)/Library/LaunchAgents"
	@sed 's|__HOME__|$(HOME)|g' "$(LAUNCHAGENT_TEMPLATE)" > "$(LAUNCHAGENT_DEST)"
	@echo "Installed LaunchAgent to $(LAUNCHAGENT_DEST)"
	@launchctl bootout gui/$$(id -u) "$(LAUNCHAGENT_DEST)" 2>/dev/null || true
	@launchctl bootstrap gui/$$(id -u) "$(LAUNCHAGENT_DEST)"
	@echo "LaunchAgent loaded ($(LAUNCHAGENT_LABEL))"

launchagent-uninstall:
	@launchctl bootout gui/$$(id -u) "$(LAUNCHAGENT_DEST)" 2>/dev/null || true
	@rm -f "$(LAUNCHAGENT_DEST)"
	@echo "Removed $(LAUNCHAGENT_DEST)"

test: dev-deps
	@PYTHONPATH=src "$(VENV_PYTHON)" -m pytest -q

lint: test lint-docs
	@"$(VENV)/bin/ruff" check src tests
	@"$(VENV)/bin/mypy" src tests
	@"$(VENV)/bin/black" --check src tests
	@"$(VENV_PYTHON)" -m py_compile src/raiplaysound_cli/*.py launcher/*.py launcher/raiplaysound-cli launcher/raiplaysound-cli-daily-sync

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
