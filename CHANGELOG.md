# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

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

### Added

- Added a packaged Python CLI implementation under `src/raiplaysound_cli/`.
- Added a Python test suite covering config parsing and core selection and
  normalization helpers.

### Removed

- Removed the legacy Bash entrypoint and the old Bash-only project constraints.

## [1.2.0] - 2026-03-03

### Added

- RSS 2.0 podcast feed generation (`download --rss`, config key `RSS_FEED`). After each download run the tool writes `feed.xml` to the show's output folder. The feed is built from all locally present audio files and enriched with metadata from the per-show cache. Re-running with all episodes already downloaded (skipped) still produces a complete, accurate feed. Off by default; use `--no-rss` to override a `RSS_FEED=true` config entry.
- `--rss-base-url <URL>` (config key `RSS_BASE_URL`): when set, RSS enclosure URLs use `<base-url>/<program_slug>/<filename>` instead of local `file://` paths, making the feed usable from any podcast client on any device. Intended for workflows where the download folder is synced to a hosted location (for example a pCloud Public Folder).
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
