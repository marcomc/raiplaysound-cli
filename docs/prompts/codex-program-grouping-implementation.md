# Codex Prompt: Program Grouping Detection Rework

Implement a filter-first grouping discovery model for RaiPlaySound programs.

Context:

- The live audit is in `docs/audits/program-grouping-report.md`.
- The full per-program data is in `docs/audits/program-grouping-audit.csv`.
- A confirmed regression is `radio2afumetti`, whose live `program.json`
  contains 18 grouping filters under the `cicli` section, but
  `raiplaysound-cli list seasons radio2afumetti` does not expose them.

Goal:

- Make `list seasons`, `list episodes`, and `download --group` work for grouped
  programs even when RaiPlaySound uses section names the CLI has never seen
  before.
- Keep proper season behavior for real season filters.
- Keep flat-program behavior unchanged when no grouping filters exist.

Implementation requirements:

1. Rework grouping discovery in `src/raiplaysound_cli/episodes.py` so
   `program.json["filters"]` is the primary source of truth.
2. Treat each filter as a candidate grouping source whenever it has a usable
   `weblink` and a stable selector key.
3. Build selector keys from:
   - `filter.path` first
   - otherwise the final segment of `filter.weblink`
   - otherwise a normalized label
4. Classify filter kinds conservatively:
   - `season` when the label or route clearly encodes a season
   - `special` when the label or route clearly encodes specials
   - `replica` when the label or route clearly encodes replicas
   - `year` when the group is explicitly a year archive
   - otherwise generic `group`
5. Do not require the route section name to be pre-known. Preserve the raw
   section name as metadata if useful, but unknown sections must still work.
6. Continue using the filter `weblink` as the source URL for grouped episode
   discovery.
7. Only fall back to the current HTML season discovery path when `filters` is
   missing or unusable.
8. Ensure programs with filter-backed groups do not silently collapse into flat
   mode.

Behavior requirements:

- `raiplaysound-cli list seasons radio2afumetti` must expose the comic title
  buckets.
- custom season sections like `raiplaysound-puntate-block` must still behave as
  seasons
- editorial groups under sections such as `clip` must remain selectable via
  `--group`
- mixed programs with specials plus other groups must remain usable
- `--season` and `--group` mutual-exclusion rules should still hold

Tests:

- Add or update unit tests in `tests/test_discovery.py` and
  `tests/test_cli_entrypoints.py`.
- Include regression coverage for:
  - `radio2afumetti`
  - a custom section carrying season labels
  - a custom non-season section carrying editorial buckets
  - a mixed program with `Speciali` plus regular groups

Validation:

- `PYTHONPATH=src .venv/bin/python -m pytest -q`
- `.venv/bin/ruff check src tests`
- `.venv/bin/mypy src tests`
- `.venv/bin/black --check src tests`
- `python -m py_compile src/raiplaysound_cli/*.py`

Documentation:

- Update `README.md` if the user-visible grouping behavior changes materially.
- Update `CHANGELOG.md` under `Unreleased`.

Deliverable:

- A patch that makes grouping detection data-driven and robust against new
  RaiPlaySound grouping route names without regressing existing season support.
