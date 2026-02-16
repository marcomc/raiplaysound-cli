SHELL := /bin/bash

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin
INSTALL_NAME ?= raiplaysound-cli
SCRIPT ?= raiplaysound-cli.sh
DEST ?= $(BINDIR)/$(INSTALL_NAME)

SHELLCHECK ?= shellcheck
MARKDOWNLINT ?= markdownlint
DOCS ?= README.md AGENTS.md TODO.md CHANGELOG.md

.PHONY: help install uninstall reinstall lint lint-shell lint-docs

help:
	@echo "Targets:"
	@echo "  make install     # Install CLI to $(DEST)"
	@echo "  make uninstall   # Remove installed CLI from $(DEST)"
	@echo "  make reinstall   # Reinstall CLI"
	@echo "  make lint        # Run shellcheck + markdownlint"
	@echo "  make lint-shell  # Run shellcheck"
	@echo "  make lint-docs   # Run markdownlint"

install: lint-shell
	@mkdir -p "$(BINDIR)"
	@cp "$(SCRIPT)" "$(DEST)"
	@chmod +x "$(DEST)"
	@echo "Installed $(DEST)"

uninstall:
	@if [[ -f "$(DEST)" ]]; then rm -f "$(DEST)"; echo "Removed $(DEST)"; else echo "Nothing to remove at $(DEST)"; fi

reinstall: uninstall install

lint: lint-shell lint-docs

lint-shell:
	@$(SHELLCHECK) --enable=all "$(SCRIPT)"

lint-docs:
	@$(MARKDOWNLINT) $(DOCS)
