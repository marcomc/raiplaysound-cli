# RaiPlaySound CLI

A Python CLI for RaiPlaySound program discovery, season and episode inspection,
incremental downloads, Rich-based transfer progress, metadata caching, RSS feed
generation, and playlist generation.

## Table of Contents

- [Installation](#installation)
- [Capabilities](#capabilities)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)

## Installation

System dependencies:

```bash
brew install python yt-dlp ffmpeg
```

Project-local install:

```bash
git clone <repo-url>
cd raiplaysound-cli
make install-dev
```

Run the CLI from the project venv:

```bash
.venv/bin/python -m raiplaysound_cli --version
```

Or install the package into the venv and use the entry point:

```bash
.venv/bin/raiplaysound-cli --version
```

## Capabilities

- Accepts either a RaiPlaySound `program_slug` or full `program_url`
- Supports `list` and `download` commands
- Lists stations, programs, seasons, and episodes
- Downloads episodes into `~/Music/RaiPlaySound/<slug>/`
- Uses `yt-dlp --download-archive` for idempotent repeat runs
- Supports audio formats `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, and `wav`
- Supports season filtering, episode ID filtering, and episode URL filtering
- Supports automatic re-download of archive-marked but missing local files
- Generates Rich-based live per-episode download progress
- Caches program catalog metadata and per-show episode metadata
- Generates optional `feed.xml` RSS output and `playlist.m3u` playlist output
- Preserves the existing `KEY=VALUE` dot-config format at
  `~/.raiplaysound-cli.conf`

## Configuration

The CLI reads optional user defaults from:

- `~/.raiplaysound-cli.conf`

Install the example config:

```bash
cp ./.raiplaysound-cli.conf.example ~/.raiplaysound-cli.conf
```

Example values:

```bash
TARGET_BASE="$HOME/Music/RaiPlaySound"
AUDIO_FORMAT="mp3"
JOBS=5
GROUP_BY="auto"
STATION_FILTER="radio2"
CATALOG_MAX_AGE_HOURS=2160
```

Supported config keys:

| Config key | CLI option | Scope |
| --- | --- | --- |
| `AUDIO_FORMAT` | `--format` | download |
| `JOBS` | `--jobs` | download |
| `SEASONS_ARG` | `--season` | download, list `--episodes` |
| `EPISODES_ARG` | `--episode-ids` | download |
| `EPISODE_URLS_ARG` | `--episode-urls` | download |
| `AUTO_REDOWNLOAD_MISSING` | `--missing` | download |
| `ENABLE_LOG` | `--log` | download |
| `DEBUG_PIDS` | `--debug-pids` | download |
| `LOG_PATH_ARG` | `--log[=PATH]` | download |
| `RSS_FEED` | `--rss` / `--no-rss` | download |
| `RSS_BASE_URL` | `--rss-base-url` | download |
| `PLAYLIST` | `--playlist` / `--no-playlist` | download |
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
| `INPUT` | `<program_slug\|program_url>` | download |

## Usage

Quick start:

```bash
.venv/bin/raiplaysound-cli list --stations
.venv/bin/raiplaysound-cli list --programs
.venv/bin/raiplaysound-cli list --episodes america7
.venv/bin/raiplaysound-cli download america7
```

Command forms:

```bash
.venv/bin/raiplaysound-cli download [OPTIONS] <program_slug|program_url>
.venv/bin/raiplaysound-cli list [OPTIONS] stations|programs
.venv/bin/raiplaysound-cli list [OPTIONS] seasons|episodes <program_slug|program_url>
```

Examples:

```bash
.venv/bin/raiplaysound-cli download musicalbox
.venv/bin/raiplaysound-cli download --format mp3 --jobs 5 musicalbox
.venv/bin/raiplaysound-cli download --season 1,2 america7
.venv/bin/raiplaysound-cli download --missing america7
.venv/bin/raiplaysound-cli download --episode-ids <id1,id2> america7
.venv/bin/raiplaysound-cli download --episode-url <episode-url> america7
.venv/bin/raiplaysound-cli download --rss --playlist musicalbox
.venv/bin/raiplaysound-cli list --stations --detailed
.venv/bin/raiplaysound-cli list --programs --filter radio2
.venv/bin/raiplaysound-cli list episodes america7 --show-urls
.venv/bin/raiplaysound-cli list seasons america7 --json
```

Output folder contents:

| File | Producer | Purpose |
| --- | --- | --- |
| `*.m4a` / `*.mp3` / ... | `yt-dlp` | Downloaded audio episodes |
| `.download-archive.txt` | `yt-dlp` | Idempotency archive |
| `.metadata-cache.tsv` | CLI | Per-show metadata cache |
| `feed.xml` | CLI | Optional RSS 2.0 podcast feed |
| `playlist.m3u` | CLI | Optional local playlist |
| `*.log` | CLI | Optional run/debug log |

## Development

Common commands:

```bash
make install-dev
make test
make lint
make lint-docs
```

Validation currently includes:

- `python -m py_compile src/raiplaysound_cli/*.py`
- `pytest`
- `markdownlint`
