# AGENTS.md

## Project Scope

This repository provides a Python-based downloader for RaiPlaySound programs.
The main goal is to download program episodes from a RaiPlaySound program slug
or URL into `~/Music/RaiPlaySound/<slug>/`, with idempotent repeat runs using
`yt-dlp --download-archive`.

## New Chat Bootstrap

- At the start of every new AI agent chat for this repository, read `README.md`.
- At the start of every new AI agent chat for this repository, read `Makefile`.
- At the start of every new AI agent chat for this repository, read
  `pyproject.toml`.
- At the start of every new AI agent chat for this repository, read
  `docs/TESTING.md`.

## Python Quality Rules

- Core implementation must stay Python-only.
- Do not reintroduce Bash as the main runtime for CLI behavior.
- Keep the package installable and executable through the Python entry point.
- Keep the CLI split across focused modules under `src/raiplaysound_cli/`
  rather than moving behavior back into one large file.
- All code changes must keep `python -m py_compile` clean.
- All code changes must keep `ruff check src tests` clean.
- All code changes must keep `mypy src tests` clean.
- All code changes must keep `black --check src tests` clean.
- All new behavior should have unit coverage where practical.

## Preferred Validation Workflow

- Use `make install` for a standalone user install under
  `~/.local/share/raiplaysound-cli/venv` with a symlink at
  `~/.local/bin/raiplaysound-cli`.
- Use `make install-dev` to refresh the local virtualenv and point
  `~/.local/bin/raiplaysound-cli` at the project `.venv` for editable
  development.
- Use `make uninstall-dev` to remove the dev symlink and restore the standalone
  install if present.
- Use `make lint` as the default full validation command.
- Use `PYTHONPATH=src .venv/bin/python -m pytest -q` for direct test runs.
- Use `.venv/bin/mypy src tests` for direct type-check runs.
- Use `raiplaysound-cli ...` for installed smoke tests and `.venv/bin/raiplaysound-cli ...`
  when the project venv path matters explicitly.

## Documentation Quality Rules

- All documentation files must pass Markdown linting.
- The line-length rule may be ignored.
- For every new CLI/config option, update Python parsing support for
  `~/.raiplaysound-cli.conf`.
- For every new CLI/config option, update `.raiplaysound-cli.conf.example` in
  project root.
- For every new CLI/config option, update `README.md` option/config
  documentation.
- After implementing any task, update the `Unreleased` section of
  `CHANGELOG.md` with user-visible changes.
- After implementing any feature, behavior change, config change, or workflow
  change relevant to users, update `README.md` accordingly.
- If an implemented task is listed in `TODO.md`, remove it from `TODO.md` and
  record it in `CHANGELOG.md` under `Unreleased`.

## Runtime Constraints

- The user-facing CLI command is `raiplaysound-cli`.
- The project still depends on external tools such as `yt-dlp` and `ffmpeg`.
- Preserve the existing dot-config file format (`KEY=VALUE`) for user defaults.
- Preserve the current output artifacts and cache/archive files in show
  directories:
  `.download-archive.txt`, `.metadata-cache.tsv`, optional `feed.xml`, and
  optional `playlist.m3u`.
- Preserve the Rich-based progress UI for downloads.
- Keep stale `.run-lock` directories recoverable; interrupted runs must not
  permanently block future downloads.

## Live Smoke Test Notes

- `list --stations` should work against the live RaiPlaySound API and is the
  fastest end-to-end smoke test after refactors.
- Program listing should continue to rely on the cached full catalog plus local
  station filtering, rather than assuming station-scoped API responses are
  reliable.
