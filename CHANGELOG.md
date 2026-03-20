# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed

- Made `raiplaysound-cli list seasons <program>` render seasons and non-season
  groupings as a compact table with program, type, name, episode count,
  selector, and published-range columns.
- Deduplicated repeated grouping rows in season/group listing output, so the
  same selector no longer appears multiple times when RaiPlaySound exposes the
  current grouping through more than one discovery path.
- Simplified grouped download hints below `list seasons` so they show generic
  `--group` usage patterns instead of repeating one command per discovered
  grouping.
- Focused top-level help output on command discovery only, leaving detailed
  options to `raiplaysound-cli list --help` and
  `raiplaysound-cli download --help`.
- Simplified top-level help further by removing embedded list-form examples so
  `raiplaysound-cli --help` stays symmetric across commands.
- Reworked `list --help` and `download --help` into clearer, sectioned help
  screens with a compact usage line, user-facing argument descriptions, grouped
  options, and short practical examples.
- Removed the generic argparse `options:` block from subcommand help in favor
  of explicit `General`, `Programs`, `Episodes`, `Selection`, and related
  sections, and hid compatibility aliases from normal help output.
- Changed `list stations` and `list programs` text output from ad-hoc line
  listings to Rich tables with clearer columns and compact next-step command
  suggestions below the table.
- Added `list --pager` (and config key `PAGER`) as an opt-in pager for text
  listing output, and clarified in help that `--refresh-catalog` applies only
  to `list programs`.
- Fixed program-catalog station enrichment to prefer Rai's `podcast_info`
  metadata, so station slugs and `list stations` program counts populate again
  after a catalog refresh.
- Reworked grouping discovery to treat `program.json` filters as the primary
  source of truth, so grouped shows with custom route names such as
  `radio2afumetti` under `cicli`, editorial `clip` buckets, and custom
  season-block sections are now exposed correctly instead of collapsing back to
  flat listings.
- Fixed year-range season handling so labels such as `2025-2026` no longer
  crash season discovery or collapse back to `Season 1` during summary and
  episode normalization.
- Fixed missing-program handling so commands such as
  `raiplaysound-cli list seasons PROGRAM_SLUG` now report a normal CLI error
  instead of leaking a Python traceback when RaiPlaySound returns `404`.
- Hardened shared HTTP handling so RaiPlaySound network failures and non-404
  HTTP responses now surface as normal CLI errors instead of raw Python
  exceptions.
- Hardened local catalog and metadata cache loading so malformed rows are
  skipped instead of aborting listings or output generation with tracebacks.
- Extended grouping discovery to read top-level `tab_menu` entries from program
  JSON, so programs that expose tabs such as `Extra` without `filters`
  metadata now show those groupings in `list seasons`.
- Refined mixed tab-menu discovery so programs with both the default `Episodi`
  surface and extra tabs show both groupings after the list cache rebuilds.
- Fixed the `Groupings` column in `list programs` so it counts the same
  discoverable groupings used by `list seasons`, including `tab_menu`-only
  tabs such as `Extra`, instead of only counting legacy `filters` entries.
- Bumped the program-catalog cache format so existing long-lived caches are
  rebuilt automatically and pick up corrected station and grouping metadata.
- Fixed `--json` output to write directly to stdout instead of through Rich, so
  piped or redirected JSON listings remain valid and are no longer corrupted by
  terminal line wrapping.
- Updated the program-grouping audit tooling and regenerated audit artifacts so
  they now record both strict payload-derived groups and the effective live
  discovery groups accepted by `list seasons`, including the small set of
  redundant default root groupings such as `episodi` or `puntate`.

## [2.1.1] - 2026-03-19 - download progress and startup visibility improvements

### Changed

- Added byte-aware per-episode download progress so active transfers now show
  size progress in megabytes while the progress bar advances gradually.
- Added explicit pre-download status messages so grouped or otherwise slow
  startup phases show what the CLI is doing before transfers begin.
- Reworked download execution into separate `yt-dlp` fetch and `ffmpeg`
  conversion stages, so completed downloads can move into a post-processing
  queue without blocking the next network download worker.
- Preserved richer seasonal audio tags in the staged conversion path by
  restoring episode titles plus season and episode numbering from the
  downloaded sidecar metadata.

## [2.1.0] - 2026-03-19 - speed improvements, grouping enhancements, and documentation additions

### Changed

- Made `raiplaysound-cli list seasons <program>` use a lightweight discovery
  path that skips metadata refreshes and avoids writing per-download metadata
  cache files during season-only listing.
- Expanded `raiplaysound-cli list seasons <program>` so it can also surface
  non-season RaiPlaySound groupings such as `speciali`, instead of always
  falling back to a flat episode list.
- Updated `raiplaysound-cli list episodes <program>` so grouped programs are
  listed across all discovered groupings, rather than only the currently
  selected subpage.
- Corrected flat program episode listings so they no longer invent a fake `S1`
  season label when RaiPlaySound exposes neither real seasons nor alternate
  groupings.
- Extended grouping discovery to cover year and period buckets, thematic
  subseries, and thin-HTML season selectors where the current season is visible
  but numbered season links are not.
- Extended grouping discovery further to read program JSON filter definitions
  when the HTML selector is incomplete, so programs such as
  `afroamerica-blackmusicrevolution` now resolve season-like paths such as
  `/episodi/2-stagione`.
- Updated `raiplaysound-cli download <program>` to reuse grouped discovery, so
  grouped programs download across their discovered collections instead of only
  the root subpage.
- Changed `raiplaysound-cli list seasons <program> --season <n>` so it now narrows
  output for real seasonal programs and rejects `--season` for non-season or
  flat programs instead of ignoring it.
- Removed the legacy list target flags (`--stations`, `--programs`,
  `--seasons`, `--episodes`) so list targets are now positional-only:
  `list stations|programs|seasons|episodes`.
- Added `--group` for `list episodes` and `download`, so non-season grouped
  programs can be narrowed to one or more discovered grouping keys or labels
  such as `speciali`.
- Updated grouping listings so each available grouping prints its exact
  selectable `--group` token and a matching `download --group ...` command.
- Added developer-facing documentation under `docs/` covering the current
  RaiPlaySound site structure assumptions, verified season URL patterns, cache
  behavior, and known discovery gaps for future contributors.
- Added `docs/COMMAND_BEHAVIOR.md` to document the expected behavior of the
  top-level CLI, `list` targets, `download`, config interaction, grouping
  behavior, and known gaps.
- Changed the empty CLI invocation and top-level help path so
  `raiplaysound-cli` now prints an extensive help message listing both commands
  and their available options.
- Clarified the caching contract in the docs and sample config: per-show
  metadata still defaults to `24` hours, while the global program catalog used
  by `list programs` intentionally defaults to `2160` hours (90 days) unless
  the user lowers it or forces a catalog refresh.
- Made `list episodes <program>` use a read-only metadata path: it reuses any
  existing per-show cache for enrichment, but no longer refreshes or rewrites
  `.metadata-cache.tsv` during listing.
- Reduced `download <program>` startup work for narrow selections by deferring
  metadata refresh until after episode filtering, so `--group`,
  `--episode-ids`, and `--episode-urls` only refresh metadata for the episodes
  that will actually be downloaded.
- Added dedicated state-dir caches for repeated `list seasons` and
  scope-specific `list episodes` calls, so list commands can reuse prior
  summaries without touching download-side metadata.
- Hardened list-only caches so stale or incompatible cached payloads are
  rebuilt automatically instead of leaking bad results into later runs.
- Bumped the list-only cache schema version again so installed CLIs rebuild old
  cached listings after the new JSON-backed grouping discovery changes.
- Reduced download startup overhead further by skipping archive/file existence
  scans unless missing-file recovery is actually enabled.

## [2.0.0] - 2026-03-10 - Python Package Port

### Changed

- Ported the project from a single Bash script to a Python package with the
  `raiplaysound-cli` entry point, preserving the `list` and `download`
  workflows, the existing dot-config file format, and the same download/output
  directories.
- Replaced the custom ANSI progress renderer with a Rich-based live transfer
  display for episode downloads.
- Updated the repository workflow, Makefile, and agent guidance for a
  Python-only architecture.
- Split the Python implementation into focused modules, added stale-lock
  recovery for interrupted download runs, corrected metadata cache validation,
  and aligned the overall Rich progress bar with episode-count semantics.
- Standardized Python development checks around `ruff`, `black`, and `mypy`.
- Changed the Makefile install workflow to match `cligoo`: standalone installs
  now live under `~/.local/share/raiplaysound-cli/venv` with the CLI exposed at
  `~/.local/bin/raiplaysound-cli`, while `install-dev` points that same command
  at the project `.venv` for editable development.
- Tightened the Makefile workflow further toward `cligoo` by moving dev setup
  to `pip install -e ".[dev]"`, adding `make run`, and making prerequisite
  checks validate Python 3.10+ explicitly.
- Added an explicit README disclaimer clarifying that the project is
  independent from RAI and RaiPlaySound and that station/program names remain
  the property of their respective owners.
- Avoided creating download directories during list-only commands.
- Made RSS and playlist generation fall back to filename-derived metadata when
  multiple cached episodes share the same publication date, avoiding
  misassigned titles and GUIDs.
- Expanded the default Markdown lint target so documentation under `docs/` is
  validated by `make lint`.
- Clarified the RSS documentation and sample config so `RSS_BASE_URL` is
  documented as a direct file-serving base URL, with generic valid and invalid
  URL shapes instead of provider-specific examples.
- Added an RSS validation step to the testing guide so users and agents can
  confirm generated enclosure URLs resolve correctly.

### Added

- Added a packaged Python CLI implementation under `src/raiplaysound_cli/`.
- Added a Python test suite covering config parsing and core selection and
  normalization helpers.
- Expanded regression coverage with tests for CLI entrypoints, RSS/playlist
  generation, downloader progress parsing, and mocked RaiPlaySound discovery
  flows.
- Added `docs/TESTING.md` to document the test suite and validation workflow
  for both users and AI agents.

### Removed

- Removed the legacy Bash entrypoint and the old Bash-only project constraints.

## [1.2.0] - 2026-03-03

### Added

- RSS 2.0 podcast feed generation (`download --rss`, config key `RSS_FEED`). After each download run the tool writes `feed.xml` to the show's output folder. The feed is built from all locally present audio files and enriched with metadata from the per-show cache. Re-running with all episodes already downloaded (skipped) still produces a complete, accurate feed. Off by default; use `--no-rss` to override a `RSS_FEED=true` config entry.
- `--rss-base-url <URL>` (config key `RSS_BASE_URL`): when set, RSS enclosure
  URLs use `<base-url>/<program_slug>/<filename>` instead of local `file://`
  paths, making the feed usable from any podcast client on any device. The
  configured base must be a direct file-serving URL, not a browser share page.
- M3U playlist generation (`download --playlist`, config key `PLAYLIST`). After each download run the tool writes `playlist.m3u` to the show's output folder. All locally present audio files are included, sorted oldest-to-newest. Paths are relative to the playlist file so the folder stays portable. Playable in VLC, mpv, and any M3U-compatible media player. Off by default; use `--no-playlist` to override a `PLAYLIST=true` config entry.

### Fixed

- RSS feed and M3U playlist now include **all locally present audio files**, not only episodes still available in RAI's online catalog. Previously, episodes removed from the RAI API were silently dropped from both outputs even though their files remained on disk. Both generators now iterate over files first and use the metadata cache only for title/GUID enrichment, falling back to filename-derived metadata for any file not in the cache.

## [1.1.1] - 2026-02-23

### Diagnostics

- Added `download --debug-pids` (and config key `DEBUG_PIDS`) to emit worker PID / `yt-dlp` PID lifecycle transitions to the debug log for diagnosis.

### Fixed

- Prevented orphan episode downloads when the main CLI process exits unexpectedly by terminating active worker jobs during cleanup.
- Corrected output naming for programs without seasons so files no longer include synthetic `S00` prefixes (for example, `Musical Box - YYYY-MM-DD - EpisodeName.m4a`).
- Hardened per-episode worker execution so `yt-dlp` is tied to worker lifecycle and cannot continue detached if a worker exits unexpectedly.
- Fixed interactive missing-file re-download prompt input handling in fish/kitty-style terminals that emit `CSI-u` key sequences (for example `^[[13u`).

## [1.1.0] - 2026-02-16

### Changed

- Redesigned CLI flow around explicit `list` and `download` commands.
- Replaced list-only flags with coherent list targets:
  - `list --stations`
  - `list --programs`
  - `list --seasons <program_slug|program_url>`
  - `list --episodes <program_slug|program_url>`
- Disambiguated episode options:
  - `list --episodes` lists episodes
  - `download --episode-ids <ids>` filters downloaded episodes by ID
  - legacy `download --episodes <ids>` is still accepted
- Replaced `--redownload-missing` with `download --missing` (legacy alias still accepted).
- Added short flags for frequent interactive actions:
  - `-m` for `--missing`
  - `-u` for `--show-urls`
- Renamed program grouping option to `--group-by` (legacy `--podcasts-group-by` still accepted).
- Updated behavior so `--group-by` is ignored with `list --stations` (no error).
- Renamed catalog refresh option to `--refresh-catalog` (legacy `--refresh-podcast-catalog` still accepted).
- Renamed station detail option to `--detailed` (legacy `--stations-detailed` still accepted).
- Renamed program station filter option to `--filter` (legacy `--station-filter` and `--station` still accepted).
- Updated CLI usage help text to reflect the new command structure and removed the in-help `Examples:` block.
- Updated README examples and guidance to the new `list`/`download` UX.
- Updated dot-config template with `COMMAND`, `LIST_TARGET`, and `DOWNLOAD_MISSING` support.
- Fixed list-mode interactions with dot-config defaults:
  - config `INPUT` is now ignored for `list --stations` and `list --programs`
  - config-only download filters (`SEASONS_ARG`, `EPISODES_ARG`, `EPISODE_URLS_ARG`) are now ignored in incompatible list targets
  - config `LIST_TARGET` is now ignored in `download` mode and no longer conflicts with explicit CLI list targets

## [1.0.0] - 2026-02-16

### Added

- Introduced `raiplaysound-cli.sh` as the main CLI entrypoint.
- Added `--version` option to print the CLI version.
- Added support for listing stations with compact mode and detailed mode (`--list-stations`, `--detailed`).
- Added support for listing programs (`--list-programs`) with grouping modes and station filtering (`--group-by`, `--filter`, `--sorted`).
- Added program year-range reporting in catalog output (for example `2018-2026`).
- Added season detection and season-aware commands (`--list-seasons`, `--list-episodes`, `--seasons`).
- Added default behavior to download latest/current season when seasons exist and none are specified.
- Added episode ID visibility in episode listings.
- Added optional episode URL visibility in episode listings (`--show-urls`).
- Added targeted episode download support by ID and URL (`--episodes`, `--episode-url`, `--episode-urls`).
- Added JSON output for all list modes (`--json`) to support automations and AI agents.
- Added per-user dot config support with CLI override precedence (`~/.raiplaysound-cli.conf`).
- Added project config template (`.raiplaysound-cli.conf.example`).
- Added metadata caching controls (`--refresh-metadata`, `--clear-metadata-cache`, `--metadata-max-age-hours`).
- Added program catalog caching controls (`--refresh-catalog`, `--catalog-max-age-hours`) with long-lived default max age.
- Added archive consistency checks and missing-file re-download flow (`--redownload-missing`).
- Added optional debug logging (`--log[=PATH]`).
- Added Bash version bootstrap to auto-reexec with Homebrew Bash when needed on macOS.
- Added aligned terminal table rendering for episode list output.
- Added this `Makefile` with `install`, `uninstall`, `reinstall`, and lint targets.
- Added this `TODO.md` file.
- Added project and naming transitions to `raiplaysound-cli`:
  - project directory renamed to `raiplaysound-cli`
  - config template renamed to `.raiplaysound-cli.conf.example`
  - default state/cache path set to `$HOME/.local/state/raiplaysound-cli/program-catalog.tsv`
  - README and CLI naming aligned to the new CLI/project naming
- Added quality and behavior improvements completed during initial development:
  - removed duplicated startup output in download mode
  - improved progress rendering for long/short episode titles
  - corrected season-selection behavior in redownload-missing flows
  - ensured metadata cache is stored in target download directories
  - ensured macOS Bash 3.2 compatibility via Homebrew Bash re-exec
