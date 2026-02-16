# RaiPlaySound CLI

A Bash CLI for RaiPlaySound program discovery and episode management.
It supports station/program catalog listing, season/episode inspection,
incremental downloads, output format conversion, metadata caching, and
parallel download execution.

## Capabilities

- Accepts either a RaiPlaySound `program_slug` (for example, `musicalbox`) or full `program_url`
- Uses two main commands: `list` and `download`
- Provides list targets for:
  - stations (`list --stations`)
  - programs (`list --programs`, optionally filtered by `--filter`)
  - seasons (`list --seasons`)
  - episodes (`list --episodes`)
- Downloads playlist/program episodes from RaiPlaySound
- Saves audio as `.m4a`
- Uses sortable file naming:
  - `Show - S0203 - YYYY-MM-DD - EpisodeName.m4a`
- Stores files in `~/Music/RaiPlaySound/<program_slug>/`
- Keeps a per-program archive file (`.download-archive.txt`) to avoid re-downloading episodes
- Optional debug logging with `--log` (disabled by default)
- Safe to run repeatedly (idempotent)
- Supports common audio output formats: `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, `wav`
- Converts only when source format differs from requested output format
- Supports parallel episode downloads (`--jobs`, default `3`)
- Shows a live per-episode progress bar (`#####-----`) with ANSI colors in interactive terminals
- Supports automatic re-download of archived-but-missing files (`download --missing`) without interactive prompt
- Supports targeted downloads:
  - by episode ID list (`--episode-ids`)
  - by episode URL (`--episode-url`, `--episode-urls`)
- Detects season numbers (from metadata or title patterns like `S2E13`) and prints selected seasons before download
- Supports season filtering for downloads (`download --season` or `download --seasons`)
- Supports season and episode discovery modes (`list --seasons`, `list --episodes`)
- Prints episode IDs in `list --episodes` output, with optional URLs via `--show-urls`
- Supports JSON output for list modes via `--json` (`stations`, `programs`, `seasons`, `episodes`)
- Lists available RaiPlaySound radio stations (`list --stations`)
- Can print detailed station listing with clickable page/feed URLs (`--detailed`)
- Lists programs in one mode at a time with smart defaults:
  - grouped by station when no station filter is set
  - grouped alphabetically when `--filter` is set
  - flat alphabetical list when `--sorted` is used
- Filters program listing by station slug (`--filter radio2` or `--filter none`)
- Caches program catalog for faster repeated `list --programs` runs
- Refreshes metadata automatically when cached data is older than 24 hours (configurable)

## Installation

1. Create or enter the project directory:

```bash
cd raiplaysound-cli
```

1. Install dependencies with Homebrew:

```bash
brew install bash yt-dlp ffmpeg
```

The CLI requires Bash 4+. On macOS it will auto-reexec with Homebrew Bash (`/opt/homebrew/bin/bash` or `/usr/local/bin/bash`) when available.

1. Make the script executable:

```bash
chmod +x ./raiplaysound-cli.sh
```

1. Optional: install/update for current user with `make`:

```bash
make install
```

This installs to `~/.local/bin/raiplaysound-cli`.

## Dot Config Defaults

The script reads an optional user config file at:

- `~/.raiplaysound-cli.conf`

Recommended format is a simple `KEY=VALUE` env-style file (Bash-friendly), not YAML/JSON/INI. This keeps parsing fast and dependency-free in pure Bash.

CLI arguments always override values from the dot config file.
`--json` is CLI-only and should not be set in the dot config file.
`--catalog-max-age-hours` is a per-run override, while `CATALOG_MAX_AGE_HOURS` in config sets the persistent default.

Install the example template from project root:

```bash
cp ./.raiplaysound-cli.conf.example ~/.raiplaysound-cli.conf
```

Then edit your defaults, for example:

```bash
TARGET_BASE="$HOME/Music/RaiPlaySound"
AUDIO_FORMAT="mp3"
JOBS=5
GROUP_BY="auto"
PODCASTS_SORTED=0
STATION_FILTER="radio2"
CATALOG_MAX_AGE_HOURS=2160
```

Config keys and matching CLI options:

| Config key | CLI option | Scope |
| --- | --- | --- |
| `AUDIO_FORMAT` | `--format` | download |
| `JOBS` | `--jobs` | download |
| `SEASONS_ARG` | `--season` | download, list `--episodes` |
| `EPISODES_ARG` | `download --episode-ids` | download |
| `EPISODE_URLS_ARG` | `--episode-url`, `--episode-urls` | download |
| `AUTO_REDOWNLOAD_MISSING` | `--missing` | download |
| `ENABLE_LOG` | `--log` | download |
| `LOG_PATH_ARG` | `--log[=PATH]` | download |
| `FORCE_REFRESH_METADATA` | `--refresh-metadata` | download |
| `CLEAR_METADATA_CACHE` | `--clear-metadata-cache` | download |
| `METADATA_MAX_AGE_HOURS` | `--metadata-max-age-hours` | download |
| `GROUP_BY` | `--group-by` | list `--programs` |
| `PODCASTS_SORTED` | `--sorted` | list `--programs` |
| `STATION_FILTER` | `--filter` | list `--programs` |
| `FORCE_REFRESH_CATALOG` | `--refresh-catalog` | list `--programs` |
| `CATALOG_MAX_AGE_HOURS` | `--catalog-max-age-hours` | list `--programs` |
| `STATIONS_DETAILED` | `--detailed` | list `--stations` |
| `SHOW_URLS` | `--show-urls` | list `--episodes` |
| `INPUT` | `<program_slug\|program_url>` | download default input |

You can still override per run:

```bash
./raiplaysound-cli.sh download --format m4a --jobs 2 musicalbox
```

`list --stations` and `list --programs` do not require a `program_slug`/`program_url`.
`list --seasons` and `list --episodes` require one.

## Usage

Quick start:

```bash
./raiplaysound-cli.sh list --stations
./raiplaysound-cli.sh list --programs
./raiplaysound-cli.sh list --episodes america7
./raiplaysound-cli.sh download america7
```

Command forms:

```bash
./raiplaysound-cli.sh download [OPTIONS] <program_slug|program_url>
./raiplaysound-cli.sh list [OPTIONS] --stations|--programs
./raiplaysound-cli.sh list [OPTIONS] --seasons|--episodes <program_slug|program_url>
```

Print CLI version:

```bash
./raiplaysound-cli.sh --version
```

Download using a `program_slug`:

```bash
./raiplaysound-cli.sh download musicalbox
```

If installed in your `PATH`, run from any directory:

```bash
raiplaysound-cli download musicalbox
```

If `INPUT="musicalbox"` is set in your dot config, you can run without arguments:

```bash
./raiplaysound-cli.sh download
```

Download using a full `program_url`:

```bash
./raiplaysound-cli.sh download https://www.raiplaysound.it/programmi/musicalbox
```

Choose output format and parallel jobs:

```bash
./raiplaysound-cli.sh download --format mp3 --jobs 5 musicalbox
```

Download only specific seasons:

```bash
./raiplaysound-cli.sh download --season 1,2 america7
```

Download all seasons:

```bash
./raiplaysound-cli.sh download --season all america7
```

Run without prompt and automatically re-download archived episodes that are missing locally:

```bash
./raiplaysound-cli.sh download --missing america7
./raiplaysound-cli.sh download -m america7
```

Enable debug log in the program download directory:

```bash
./raiplaysound-cli.sh download --log america7
```

Enable debug log in a specific file path:

```bash
./raiplaysound-cli.sh download --log=/tmp/raiplaysound-debug.log america7
```

Force metadata refresh:

```bash
./raiplaysound-cli.sh download --refresh-metadata america7
```

Clear metadata cache manually:

```bash
./raiplaysound-cli.sh download --clear-metadata-cache america7
```

Set metadata cache max age in hours:

```bash
./raiplaysound-cli.sh download --metadata-max-age-hours 6 america7
```

When to clear metadata cache manually:

- `list --seasons` or `list --episodes` output looks inconsistent after major site-side changes.
- You suspect cached metadata is corrupted (for example, missing titles/dates for many known episodes).
- You want to force a clean rebuild and avoid waiting for automatic cache expiration.

List available seasons (with inferred publication year range):

```bash
./raiplaysound-cli.sh list --seasons america7
```

List episodes for one or more seasons:

```bash
./raiplaysound-cli.sh list --episodes --season 2 america7
```

List episodes including URLs:

```bash
./raiplaysound-cli.sh list --episodes --show-urls --season 2 america7
./raiplaysound-cli.sh list --episodes -u --season 2 america7
```

List episodes as JSON (automation/agent-friendly):

```bash
./raiplaysound-cli.sh list --episodes --season 2 --json america7
```

If `list --episodes` is used without `--season`, it lists the latest detected season.

If `download` is run without `--season`, it targets the current/latest season only.

`list --episodes` lists episodes. In download mode, use `--episode-ids`.

Download only selected episodes by ID:

```bash
./raiplaysound-cli.sh download --episode-ids da038798-68f0-489b-9aa9-dc8b5cc45d64 musicalbox
./raiplaysound-cli.sh download --episode-ids id1,id2,id3 america7
```

Download only selected episodes by URL:

```bash
./raiplaysound-cli.sh download --episode-url https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html musicalbox
./raiplaysound-cli.sh download --episode-urls https://www.raiplaysound.it/audio/...html,https://www.raiplaysound.it/audio/...html america7
```

List all available radio stations:

```bash
./raiplaysound-cli.sh list --stations
```

Output is compact and includes station slugs (for filters), for example:

- `radio1`
- `radio2`
- `radio3`
- `isoradio`
- `nonameradio`

List stations with detailed URLs (station page and feed):

```bash
./raiplaysound-cli.sh list --stations --detailed
```

List stations as JSON:

```bash
./raiplaysound-cli.sh list --stations --json
```

List programs using default grouping behavior:

```bash
./raiplaysound-cli.sh list --programs
```

List programs as JSON:

```bash
./raiplaysound-cli.sh list --programs --json
```

Force-refresh program catalog cache:

```bash
./raiplaysound-cli.sh list --programs --refresh-catalog
```

List all programs grouped only by station:

```bash
./raiplaysound-cli.sh list --programs --group-by station
```

List as a flat alphabetical list (no groups):

```bash
./raiplaysound-cli.sh list --programs --sorted
```

List only programs for one station slug:

```bash
./raiplaysound-cli.sh list --programs --filter radio2
```

List only programs without an assigned station:

```bash
./raiplaysound-cli.sh list --programs --filter none
```

Set program catalog cache max age in hours:

```bash
./raiplaysound-cli.sh list --programs --catalog-max-age-hours 12
```

Use `--catalog-max-age-hours` for a one-off run; set `CATALOG_MAX_AGE_HOURS` in `~/.raiplaysound-cli.conf` for a persistent default.

## Compatibility Aliases

Primary docs and examples use canonical options, but the following aliases are still accepted for backward compatibility:

- `--list-programs` -> `list --programs`
- `--list-stations` -> `list --stations`
- `--list-seasons` -> `list --seasons`
- `--list-episodes` -> `list --episodes`
- `--station` and `--station-filter` -> `--filter`
- `--podcasts-group-by` -> `--group-by`
- `--refresh-podcast-catalog` -> `--refresh-catalog`
- `--stations-detailed` -> `--detailed`
- `download --episodes` -> `download --episode-ids`
- `--redownload-missing` -> `--missing`

Reference episode example for this program:

- [Musical Box episode example](https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html)

## Cron Example

Run daily at 06:30:

```cron
30 6 * * * /usr/local/bin/raiplaysound-cli download musicalbox
```

## How `--download-archive` Works

The script uses `--download-archive` with:

- `~/Music/RaiPlaySound/<program_slug>/.download-archive.txt`

Each downloaded episode ID is recorded in that file. On later runs, `yt-dlp` checks the archive and skips episodes already present there. This makes repeated runs incremental and prevents duplicate downloads.
