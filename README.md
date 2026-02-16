# RaiPlaySound CLI

A Bash CLI for RaiPlaySound program discovery and episode management.
It supports station/program catalog listing, season/episode inspection,
incremental downloads, output format conversion, metadata caching, and
parallel download execution.

## Capabilities

- Accepts either a RaiPlaySound slug (for example, `musicalbox`) or full program URL
- Provides catalog/listing commands for:
  - stations (`--list-stations`)
  - programs (`--list-programs`, optionally filtered by `--station`)
  - seasons (`--list-seasons`)
  - episodes (`--list-episodes`)
- Downloads playlist/program episodes from RaiPlaySound
- Saves audio as `.m4a`
- Uses sortable file naming:
  - `Show - S0203 - YYYY-MM-DD - EpisodeName.m4a`
- Stores files in `~/Music/RaiPlaySound/<slug>/`
- Keeps a per-program archive file (`.download-archive.txt`) to avoid re-downloading episodes
- Optional debug logging with `--log` (disabled by default)
- Safe to run repeatedly (idempotent)
- Supports common audio output formats: `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, `wav`
- Converts only when source format differs from requested output format
- Supports parallel episode downloads (`--jobs`, default `3`)
- Shows a live per-episode progress bar (`#####-----`) with ANSI colors in interactive terminals
- Supports automatic re-download of archived-but-missing files (`--redownload-missing`) without interactive prompt
- Supports targeted downloads:
  - by episode ID list (`--episodes`)
  - by episode URL (`--episode-url`, `--episode-urls`)
- Detects season numbers (from metadata or title patterns like `S2E13`) and prints selected seasons before download
- Supports season filtering for downloads (`--seasons`)
- Supports season and episode discovery modes (`--list-seasons`, `--list-episodes`)
- Prints episode IDs in `--list-episodes` output, with optional URLs via `--show-urls`
- Supports JSON output for list modes via `--json` (`stations`, `programs`, `seasons`, `episodes`)
- Lists available RaiPlaySound radio stations (`--list-stations`)
- Can print detailed station listing with clickable page/feed URLs (`--stations-detailed`)
- Lists programs in one mode at a time with smart defaults:
  - grouped by station when no station filter is set
  - grouped alphabetically when `--station` is set
  - flat alphabetical list when `--sorted` is used
- Filters program listing by station short name (`--station radio2` or `--station none`)
- Caches program catalog for faster repeated `--list-programs` runs
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

Install the example template from project root:

```bash
cp ./.raiplaysound-cli.conf.example ~/.raiplaysound-cli.conf
```

Then edit your defaults, for example:

```bash
TARGET_BASE="$HOME/Music/RaiPlaySound"
AUDIO_FORMAT="mp3"
JOBS=5
PODCASTS_GROUP_BY="auto"
PODCASTS_SORTED=0
STATION_FILTER="radio2"
CATALOG_MAX_AGE_HOURS=2160
```

You can still override per run:

```bash
./raiplaysound-cli.sh --format m4a --jobs 2 musicalbox
```

List modes do not require a slug/URL.

## Usage

Run using a slug:

```bash
./raiplaysound-cli.sh musicalbox
```

If installed in your `PATH`, run from any directory:

```bash
raiplaysound-cli.sh musicalbox
```

If `INPUT="musicalbox"` is set in your dot config, you can run without arguments:

```bash
./raiplaysound-cli.sh
```

Run using a full program URL:

```bash
./raiplaysound-cli.sh https://www.raiplaysound.it/programmi/musicalbox
```

Run and choose output format:

```bash
./raiplaysound-cli.sh --format mp3 musicalbox
```

Run with custom parallelism:

```bash
./raiplaysound-cli.sh --jobs 5 musicalbox
```

Run with format and parallelism:

```bash
./raiplaysound-cli.sh --format m4a --jobs 3 musicalbox
```

Download only specific seasons:

```bash
./raiplaysound-cli.sh --seasons 1,2 america7
```

Download all seasons:

```bash
./raiplaysound-cli.sh --seasons all america7
```

Run without prompt and automatically re-download archived episodes that are missing locally:

```bash
./raiplaysound-cli.sh --redownload-missing america7
```

Enable debug log in the program download directory:

```bash
./raiplaysound-cli.sh --log america7
```

Enable debug log in a specific file path:

```bash
./raiplaysound-cli.sh --log=/tmp/raiplaysound-debug.log america7
```

Force metadata refresh:

```bash
./raiplaysound-cli.sh --refresh-metadata america7
```

Clear metadata cache manually:

```bash
./raiplaysound-cli.sh --clear-metadata-cache america7
```

Set metadata cache max age in hours:

```bash
./raiplaysound-cli.sh --metadata-max-age-hours 6 america7
```

When to clear metadata cache manually:

- `--list-seasons` or `--list-episodes` output looks inconsistent after major site-side changes.
- You suspect cached metadata is corrupted (for example, missing titles/dates for many known episodes).
- You want to force a clean rebuild and avoid waiting for automatic cache expiration.

List available seasons (with inferred publication year range):

```bash
./raiplaysound-cli.sh --list-seasons america7
```

List episodes for one or more seasons:

```bash
./raiplaysound-cli.sh --list-episodes --seasons 2 america7
```

List episodes including URLs:

```bash
./raiplaysound-cli.sh --list-episodes --show-urls --seasons 2 america7
```

List episodes as JSON (automation/agent-friendly):

```bash
./raiplaysound-cli.sh --list-episodes --seasons 2 --json america7
```

If `--list-episodes` is used without `--seasons`, it lists the latest detected season.

If download is run without `--seasons`, it targets the current/latest season only.

Download only selected episodes by ID:

```bash
./raiplaysound-cli.sh --episodes da038798-68f0-489b-9aa9-dc8b5cc45d64 musicalbox
./raiplaysound-cli.sh --episodes id1,id2,id3 america7
```

Download only selected episodes by URL:

```bash
./raiplaysound-cli.sh --episode-url https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html musicalbox
./raiplaysound-cli.sh --episode-urls https://www.raiplaysound.it/audio/...html,https://www.raiplaysound.it/audio/...html america7
```

List all available radio stations:

```bash
./raiplaysound-cli.sh --list-stations
```

Output is compact and includes station short names (for filters), for example:

- `radio1`
- `radio2`
- `radio3`
- `isoradio`
- `nonameradio`

List stations with detailed URLs (station page and feed):

```bash
./raiplaysound-cli.sh --list-stations --stations-detailed
```

List stations as JSON:

```bash
./raiplaysound-cli.sh --list-stations --json
```

List programs using default grouping behavior:

```bash
./raiplaysound-cli.sh --list-programs
```

List programs as JSON:

```bash
./raiplaysound-cli.sh --list-programs --json
```

Legacy alias still accepted: `--list-podcasts` (deprecated).

Force-refresh program catalog cache:

```bash
./raiplaysound-cli.sh --refresh-podcast-catalog --list-programs
```

List all programs grouped only by station:

```bash
./raiplaysound-cli.sh --list-programs --podcasts-group-by station
```

List as a flat alphabetical list (no groups):

```bash
./raiplaysound-cli.sh --list-programs --sorted
```

List only programs for one station short name:

```bash
./raiplaysound-cli.sh --list-programs --station radio2
```

List only programs without an assigned station:

```bash
./raiplaysound-cli.sh --list-programs --station none
```

Set program catalog cache max age in hours:

```bash
./raiplaysound-cli.sh --catalog-max-age-hours 12 --list-programs
```

## Option Examples

```bash
# Help
./raiplaysound-cli.sh --help

# Download mode
./raiplaysound-cli.sh musicalbox
./raiplaysound-cli.sh --format mp3 --jobs 4 musicalbox
./raiplaysound-cli.sh --seasons 1,2 america7
./raiplaysound-cli.sh --seasons all america7
./raiplaysound-cli.sh --redownload-missing america7
./raiplaysound-cli.sh --episodes id1,id2 america7
./raiplaysound-cli.sh --episode-url https://www.raiplaysound.it/audio/...html musicalbox

# Metadata cache controls
./raiplaysound-cli.sh --refresh-metadata america7
./raiplaysound-cli.sh --clear-metadata-cache america7
./raiplaysound-cli.sh --metadata-max-age-hours 12 america7

# Logging
./raiplaysound-cli.sh --log america7
./raiplaysound-cli.sh --log=/tmp/raiplaysound-debug.log america7

# Season/episode listing
./raiplaysound-cli.sh --list-seasons america7
./raiplaysound-cli.sh --list-episodes --seasons 2 america7
./raiplaysound-cli.sh --list-episodes --show-urls --seasons 2 america7
./raiplaysound-cli.sh --list-episodes --seasons 2 --json america7

# Station listing
./raiplaysound-cli.sh --list-stations
./raiplaysound-cli.sh --list-stations --stations-detailed
./raiplaysound-cli.sh --list-stations --json

# Program listing
./raiplaysound-cli.sh --list-programs
./raiplaysound-cli.sh --list-programs --station radio2
./raiplaysound-cli.sh --list-programs --station none
./raiplaysound-cli.sh --list-programs --podcasts-group-by station
./raiplaysound-cli.sh --list-programs --podcasts-group-by alpha
./raiplaysound-cli.sh --list-programs --sorted
./raiplaysound-cli.sh --list-programs --json
./raiplaysound-cli.sh --refresh-podcast-catalog --list-programs
./raiplaysound-cli.sh --catalog-max-age-hours 2160 --list-programs
```

Reference episode example for this program:

- [Musical Box episode example](https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html)

## Cron Example

Run daily at 06:30:

```cron
30 6 * * * /usr/local/bin/raiplaysound-cli.sh musicalbox
```

## How `--download-archive` Works

The script uses `--download-archive` with:

- `~/Music/RaiPlaySound/<slug>/.download-archive.txt`

Each downloaded episode ID is recorded in that file. On later runs, `yt-dlp` checks the archive and skips episodes already present there. This makes repeated runs incremental and prevents duplicate downloads.
