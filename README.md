# RaiPlaySound Podcast Downloader

A Bash-based downloader for RaiPlaySound programs that accepts a podcast slug or full program URL, downloads all episodes, and keeps future runs incremental using `yt-dlp --download-archive`.

## Features

- Accepts either a RaiPlaySound slug (for example, `musicalbox`) or full program URL
- Downloads playlist/program episodes from RaiPlaySound
- Saves audio as `.m4a`
- Uses sortable file naming:
  - `Show - S0203 - YYYY-MM-DD - EpisodeName.m4a`
- Stores files in `~/Music/RaiPlaySound/<slug>/`
- Keeps a per-podcast archive file (`.download-archive.txt`) to avoid re-downloading episodes
- Optional debug logging with `--log` (disabled by default)
- Safe to run repeatedly (idempotent)
- Supports common podcast output formats: `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, `wav`
- Converts only when source format differs from requested output format
- Supports parallel episode downloads (`--jobs`, default `3`)
- Shows a live per-episode progress bar (`#####-----`) with ANSI colors in interactive terminals
- Supports automatic re-download of archived-but-missing files (`--redownload-missing`) without interactive prompt
- Detects season numbers (from metadata or title patterns like `S2E13`) and prints selected seasons before download
- Supports season filtering for downloads (`--seasons`)
- Supports season and episode discovery modes (`--list-seasons`, `--list-episodes`)
- Lists available RaiPlaySound radio stations (`--list-stations`)
- Lists all podcasts, grouped alphabetically and/or by station (`--list-podcasts`, `--podcasts-group-by`)
- Refreshes metadata automatically when cached data is older than 24 hours (configurable)

## Installation

1. Create or enter the project directory:

```bash
cd raiplaysound-downloader
```

1. Install dependencies with Homebrew:

```bash
brew install yt-dlp ffmpeg
```

1. Make the script executable:

```bash
chmod +x ./raiplaysound-podcast.sh
```

## Dot Config Defaults

The script reads an optional user config file at:

- `~/.raiplaysound-downloader.conf`

Recommended format is a simple `KEY=VALUE` env-style file (Bash-friendly), not YAML/JSON/INI. This keeps parsing fast and dependency-free in pure Bash.

CLI arguments always override values from the dot config file.

Install the example template from project root:

```bash
cp ./.raiplaysound-downloader.conf.example ~/.raiplaysound-downloader.conf
```

Then edit your defaults, for example:

```bash
TARGET_BASE="$HOME/Music/RaiPlaySound"
AUDIO_FORMAT="mp3"
JOBS=5
PODCASTS_GROUP_BY="both"
```

You can still override per run:

```bash
./raiplaysound-podcast.sh --format m4a --jobs 2 musicalbox
```

List modes do not require a slug/URL.

## Usage

Run using a slug:

```bash
./raiplaysound-podcast.sh musicalbox
```

If installed in your `PATH`, run from any directory:

```bash
raiplaysound-podcast.sh musicalbox
```

If `INPUT="musicalbox"` is set in your dot config, you can run without arguments:

```bash
./raiplaysound-podcast.sh
```

Run using a full program URL:

```bash
./raiplaysound-podcast.sh https://www.raiplaysound.it/programmi/musicalbox
```

Run and choose output format:

```bash
./raiplaysound-podcast.sh --format mp3 musicalbox
```

Run with custom parallelism:

```bash
./raiplaysound-podcast.sh --jobs 5 musicalbox
```

Run with format and parallelism:

```bash
./raiplaysound-podcast.sh --format m4a --jobs 3 musicalbox
```

Download only specific seasons:

```bash
./raiplaysound-podcast.sh --seasons 1,2 america7
```

Download all seasons:

```bash
./raiplaysound-podcast.sh --seasons all america7
```

Run without prompt and automatically re-download archived episodes that are missing locally:

```bash
./raiplaysound-podcast.sh --redownload-missing america7
```

Enable debug log in the podcast download directory:

```bash
./raiplaysound-podcast.sh --log america7
```

Enable debug log in a specific file path:

```bash
./raiplaysound-podcast.sh --log=/tmp/raiplaysound-debug.log america7
```

Force metadata refresh:

```bash
./raiplaysound-podcast.sh --refresh-metadata america7
```

Clear metadata cache manually:

```bash
./raiplaysound-podcast.sh --clear-metadata-cache america7
```

Set metadata cache max age in hours:

```bash
./raiplaysound-podcast.sh --metadata-max-age-hours 6 america7
```

When to clear metadata cache manually:

- `--list-seasons` or `--list-episodes` output looks inconsistent after major site-side changes.
- You suspect cached metadata is corrupted (for example, missing titles/dates for many known episodes).
- You want to force a clean rebuild and avoid waiting for automatic cache expiration.

List available seasons (with inferred publication year range):

```bash
./raiplaysound-podcast.sh --list-seasons america7
```

List episodes for one or more seasons:

```bash
./raiplaysound-podcast.sh --list-episodes --seasons 2 america7
```

If `--list-episodes` is used without `--seasons`, it lists the latest detected season.

If download is run without `--seasons`, it targets the current/latest season only.

List all available radio stations:

```bash
./raiplaysound-podcast.sh --list-stations
```

List all podcasts (both alphabetic and by station):

```bash
./raiplaysound-podcast.sh --list-podcasts
```

List all podcasts grouped only by station:

```bash
./raiplaysound-podcast.sh --list-podcasts --podcasts-group-by station
```

Reference episode example for this program:

- [Musical Box episode example](https://www.raiplaysound.it/audio/2026/02/Musical-Box-del-15022026-da038798-68f0-489b-9aa9-dc8b5cc45d64.html)

## Cron Example

Run daily at 06:30:

```cron
30 6 * * * /usr/local/bin/raiplaysound-podcast.sh musicalbox
```

## How `--download-archive` Works

The script uses `--download-archive` with:

- `~/Music/RaiPlaySound/<slug>/.download-archive.txt`

Each downloaded episode ID is recorded in that file. On later runs, `yt-dlp` checks the archive and skips episodes already present there. This makes repeated runs incremental and prevents duplicate downloads.
