# Changelog

All notable changes to this project are documented in this file.

## [1.0.0] - 2026-02-16

### Added

- Introduced `raiplaysound-cli.sh` as the main CLI entrypoint.
- Added `--version` option to print the CLI version.
- Added support for listing stations with compact mode and detailed mode (`--list-stations`, `--stations-detailed`).
- Added support for listing programs (`--list-programs`) with grouping modes and station filtering (`--podcasts-group-by`, `--station`, `--sorted`).
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
- Added program catalog caching controls (`--refresh-podcast-catalog`, `--catalog-max-age-hours`) with long-lived default max age.
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
