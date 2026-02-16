# AGENTS.md

## Project Scope

This repository provides a Bash-based downloader for RaiPlaySound podcasts.
The main goal is to download podcast episodes from a RaiPlaySound program slug or URL into `~/Music/RaiPlaySound/<slug>/`, with idempotent repeat runs using `yt-dlp --download-archive`.

## Bash Quality Rules

- All Bash scripts must pass `shellcheck --enable=all`.
- ShellCheck warnings and errors must be fixed in code.
- Do not silence ShellCheck diagnostics with disable directives.

## Documentation Quality Rules

- All documentation files must pass Markdown linting.
- The line-length rule may be ignored.

## Scripting Constraints

- Do not embed or include Python in Bash scripting for this project.
- Implement scripting logic in Bash only.
