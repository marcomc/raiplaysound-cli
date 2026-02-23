# AGENTS.md

## Project Scope

This repository provides a Bash-based downloader for RaiPlaySound programs.
The main goal is to download program episodes from a RaiPlaySound program slug or URL into `~/Music/RaiPlaySound/<slug>/`, with idempotent repeat runs using `yt-dlp --download-archive`.

## New Chat Bootstrap

- At the start of every new AI agent chat for this repository, read `README.md`.
- At the start of every new AI agent chat for this repository, read `Makefile`.

## Bash Quality Rules

- All Bash scripts must pass `shellcheck --enable=all`.
- ShellCheck warnings and errors must be fixed in code.
- Do not silence ShellCheck diagnostics with disable directives.

## Documentation Quality Rules

- All documentation files must pass Markdown linting.
- The line-length rule may be ignored.
- For every new CLI/config option, update script parsing support for `~/.raiplaysound-cli.conf`.
- For every new CLI/config option, update `.raiplaysound-cli.conf.example` in project root.
- For every new CLI/config option, update `README.md` option/config documentation.
- After implementing any task, update the `Unreleased` section of `CHANGELOG.md` with user-visible changes.
- After implementing any feature, behavior change, config change, or workflow change relevant to users, update `README.md` accordingly.
- If an implemented task is listed in `TODO.md`, remove it from `TODO.md` and record it in `CHANGELOG.md` under `Unreleased`.

## Scripting Constraints

- Do not embed or include Python in Bash scripting for this project.
- Implement scripting logic in Bash only.
