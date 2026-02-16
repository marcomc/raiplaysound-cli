# Changelog

All notable changes to this project are documented in this file.

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
