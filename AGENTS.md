# AGENTS.md

## Project Scope

This repository provides a Python-based downloader for RaiPlaySound programs.
The main goal is to download program episodes from a RaiPlaySound program slug
or URL into `~/Music/RaiPlaySound/<slug>/`, with idempotent repeat runs using
`yt-dlp --download-archive`.

## New Chat Bootstrap

- At the start of every new AI agent chat for this repository, read `README.md`.
- At the start of every new AI agent chat for this repository, read `Makefile`.

## Python Quality Rules

- Core implementation must stay Python-only.
- Do not reintroduce Bash as the main runtime for CLI behavior.
- Keep the package installable and executable through the Python entry point.
- All code changes must keep `python -m py_compile` clean.
- All new behavior should have unit coverage where practical.

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
