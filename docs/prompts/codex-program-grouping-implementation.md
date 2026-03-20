# Codex Prompt: Program Grouping Discovery Rework

Implement a grouping discovery model for RaiPlaySound programs that uses the
same discoverable grouping surfaces everywhere in the CLI.

Context:

- The live audit is in `docs/audits/program-grouping-report.md`.
- The full per-program data is in `docs/audits/program-grouping-audit.csv`.
- Developer notes document that some programs expose groupings through
  `program.json["tab_menu"]`, not only through `program.json["filters"]`.
- Mixed cases exist where the root `Episodi` surface must coexist with
  additional tab-backed groups such as `Extra`, `Clip`, `Audiolibri`, or
  `Playlist`.

Goal:

- Make `list seasons`, `list episodes`, `download --group`, and the
  `Groupings` column in `list programs` use the same grouping discovery logic.
- Support grouped programs even when RaiPlaySound uses route names the CLI has
  never seen before.
- Preserve correct season behavior for real seasons.
- Preserve root `Episodi` when it should coexist with tab-backed groupings.

Implementation requirements:

1. Centralize grouping discovery in `src/raiplaysound_cli/episodes.py`.
2. Use both:
   - `program.json["filters"]`
   - `program.json["tab_menu"]`
3. Treat any discoverable entry with a usable URL and stable selector key as a
   candidate grouping source.
4. Do not discard the active root `/programmi/<slug>` tab when non-root tabs
   also exist, because that root often represents the main `Episodi` surface.
5. Build selector keys from:
   - route path first when available
   - otherwise the final segment of the grouping URL
   - otherwise a normalized label
6. Classify grouping kinds conservatively:
   - `season` when the label or route clearly encodes a season
   - `special` when the label or route clearly encodes specials
   - `replica` when the label or route clearly encodes replicas
   - `year` when the group is explicitly a year archive
   - otherwise generic `group`
7. Do not require the route section name to be pre-known.
8. Keep grouped programs from silently collapsing into flat mode.
9. When a discoverable grouping page fails to enumerate through the normal
   playlist path, fall back to page JSON card extraction.

Behavior requirements:

- `raiplaysound-cli list seasons radio2afumetti` must expose the comic-title
  buckets.
- tab-menu-only programs with `Extra`, `Clip`, `Audiolibri`, or `Playlist`
  must remain selectable.
- mixed programs must preserve the root `Episodi` surface alongside other tabs.
- custom season sections like `raiplaysound-puntate-block` must still behave as
  seasons.
- mixed programs with `Speciali` plus other groups must remain usable.
- `list seasons` and the `Groupings` column in `list programs` must be derived
  from the same discoverable grouping surfaces.

Tests:

- Add or update unit tests in `tests/test_discovery.py`,
  `tests/test_cli_entrypoints.py`, and any other affected test modules.
- Include regression coverage for:
  - `radio2afumetti`
  - a custom section carrying season labels
  - a tab-menu-only program with root `Episodi` plus `Extra`
  - a tab-menu-only program with root `Episodi` plus `Clip`
  - a mixed program where root `Episodi` must coexist with tab-backed groups
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

- A patch that makes grouping discovery data-driven across both `filters` and
  `tab_menu`, preserves mixed root-plus-tab layouts, and keeps audit/reporting
  logic aligned with CLI behavior.
