PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
MARKDOWNLINT ?= markdownlint
DOCS := README.md AGENTS.md TODO.md CHANGELOG.md

.PHONY: help venv install install-dev test lint lint-docs clean

help:
	@echo "Targets:"
	@echo "  make venv        # Create project virtualenv"
	@echo "  make install     # Install package into project virtualenv"
	@echo "  make install-dev # Install package + test deps into project virtualenv"
	@echo "  make test        # Run unit tests"
	@echo "  make lint        # Run compile check + tests + markdownlint"
	@echo "  make lint-docs   # Run markdownlint"
	@echo "  make clean       # Remove build/test artifacts"

venv:
	@$(PYTHON) -m venv "$(VENV)"

install: venv
	@"$(VENV_PYTHON)" -m pip install --no-build-isolation .

install-dev: venv
	@"$(VENV_PYTHON)" -m pip install setuptools wheel rich pytest pytest-cov
	@"$(VENV_PYTHON)" -m pip install --no-build-isolation -e .

test: install-dev
	@PYTHONPATH=src "$(VENV_PYTHON)" -m pytest -q

lint: test lint-docs
	@"$(VENV_PYTHON)" -m py_compile src/raiplaysound_cli/*.py

lint-docs:
	@$(MARKDOWNLINT) $(DOCS)

clean:
	@rm -rf "$(VENV)" .pytest_cache .coverage __pycache__ src/*.egg-info dist build
