# Test Suite Guide

This document explains the automated test and validation workflow for
`raiplaysound-cli`, both for human contributors and for AI agents working in
the repository.

## Table of Contents

- [Scope](#scope)
- [Validation Layers](#validation-layers)
- [Test Modules](#test-modules)
- [Common Commands](#common-commands)
- [When to Run What](#when-to-run-what)
- [Agent Guidance](#agent-guidance)
- [Live Smoke Tests](#live-smoke-tests)

## Scope

The repository has two categories of validation:

1. static and quality checks
2. automated tests

The goal is to catch:

- packaging and install regressions
- CLI argument and dispatch regressions
- metadata and cache handling regressions
- downloader progress parsing regressions
- RSS and playlist output regressions
- RaiPlaySound discovery regressions at the mocked boundary

## Validation Layers

The default full validation command is:

```bash
make lint
```

That runs:

- `pytest`
- `ruff check src tests`
- `mypy src tests`
- `black --check src tests`
- `python -m py_compile src/raiplaysound_cli/*.py`
- Markdown lint for project docs

Use this when a change affects behavior, packaging, tests, or documentation.

## Test Modules

Current test coverage is split by concern.

### Core utility and safety checks

File:

- [`tests/test_cli_utils.py`](/Users/mmassari/Development/raiplaysound-cli/tests/test_cli_utils.py)

Covers:

- config parsing
- boolean normalization
- config path expansion
- season and episode filter parsing
- metadata normalization
- cache format and freshness checks
- cache entry completeness checks
- invalid integer config handling
- stale lock recovery

### CLI entrypoint and argument behavior

File:

- [`tests/test_cli_entrypoints.py`](/Users/mmassari/Development/raiplaysound-cli/tests/test_cli_entrypoints.py)

Covers:

- `python -m raiplaysound_cli --version`
- config-driven list behavior
- JSON output shape for list-mode paths

### RSS and playlist generation

File:

- [`tests/test_outputs.py`](/Users/mmassari/Development/raiplaysound-cli/tests/test_outputs.py)

Covers:

- RSS feed generation from local files plus metadata cache
- filename fallback behavior when metadata is missing
- playlist ordering and title selection

### Downloader progress parsing

File:

- [`tests/test_downloads.py`](/Users/mmassari/Development/raiplaysound-cli/tests/test_downloads.py)

Covers:

- parsing `yt-dlp` progress lines
- byte progress updates
- archive-skip handling

These tests are mocked. They do not start a real `yt-dlp` process.

### RaiPlaySound discovery and catalog logic

File:

- [`tests/test_discovery.py`](/Users/mmassari/Development/raiplaysound-cli/tests/test_discovery.py)

Covers:

- station and program metadata parsing
- season-source discovery from RaiPlaySound HTML
- episode deduplication and season assignment from mocked `yt-dlp` output

These tests intentionally mock network and command boundaries instead of using
live RaiPlaySound responses.

## Common Commands

Create or refresh the development environment:

```bash
make install-dev
```

Run only the Python tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Run a specific test file:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_outputs.py
```

Run static checks individually:

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy src tests
.venv/bin/black --check src tests
.venv/bin/python -m py_compile src/raiplaysound_cli/*.py
```

Run everything:

```bash
make lint
```

## When to Run What

Use this table as the default rule.

| Change type | Minimum expected validation |
| --- | --- |
| README, AGENTS, changelog, docs only | `markdownlint` on changed docs |
| test-only changes | `pytest`, `ruff`, `black --check`, `mypy` |
| config parsing or CLI dispatch changes | `make lint` |
| downloader, progress, or output generation changes | `make lint` |
| install or packaging changes | `make lint`, plus install smoke checks |
| RaiPlaySound discovery changes | `make lint`, plus at least one live smoke test |

## Agent Guidance

AI agents working in this repository should follow these rules:

1. prefer mocked unit tests for deterministic regressions
2. avoid relying only on live RaiPlaySound checks
3. use `make lint` before considering substantial work complete
4. update tests when changing:
   - CLI argument behavior
   - output file formats
   - cache semantics
   - downloader progress parsing
   - discovery/catalog logic
5. document new validation workflows in:
   - [`README.md`](/Users/mmassari/Development/raiplaysound-cli/README.md)
   - [`AGENTS.md`](/Users/mmassari/Development/raiplaysound-cli/AGENTS.md)
   - [`CHANGELOG.md`](/Users/mmassari/Development/raiplaysound-cli/CHANGELOG.md)

## Live Smoke Tests

The automated suite is intentionally mostly mocked. A small number of live
checks are still useful after substantial changes.

Recommended live smoke tests:

```bash
raiplaysound-cli list --stations
raiplaysound-cli list --programs --filter radio2
raiplaysound-cli list seasons america7
raiplaysound-cli list episodes america7 --json
```

If download behavior was changed, also run a small real download against a
temporary `HOME` or a temporary target directory so local archives and media
files do not pollute the main environment.
