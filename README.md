# RaiPlaySound CLI

A Python CLI for RaiPlaySound program discovery, season and episode inspection,
incremental downloads, Rich-based transfer progress, metadata caching, RSS feed
generation, and playlist generation.

> **Disclaimer:** RaiPlaySound CLI is an independent, community-developed
> project and is **not** affiliated with, endorsed by, or in any way officially
> connected with RAI, RaiPlaySound, or the official RaiPlaySound application.
> "RAI", "RaiPlaySound", radio station names, program names, show titles, and
> related marks remain the property of their respective owners. This tool
> references publicly accessible RaiPlaySound web resources only to help users
> inspect programs and download episodes they already have access to. It is
> provided as a free, open-source convenience utility for users who prefer a
> terminal-based workflow.

## Table of Contents

- [Installation](#installation)
- [Capabilities](#capabilities)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Disclaimer](#disclaimer)

## Installation

Requirements:

- Python 3.10+
- `yt-dlp`
- `ffmpeg`

System dependency example on macOS:

```bash
brew install python yt-dlp ffmpeg
```

Standalone user install:

```bash
git clone <repo-url>
cd raiplaysound-cli
make install
```

This installs the package into:

- `~/.local/share/raiplaysound-cli/venv`

and creates the user-facing command at:

- `~/.local/bin/raiplaysound-cli`

Editable development install:

```bash
git clone <repo-url>
cd raiplaysound-cli
make install-dev
```

`make install-dev` keeps the command in `~/.local/bin/raiplaysound-cli`, but
points it at the project-local `.venv` so source edits take effect immediately.

Run the CLI from the user install:

```bash
~/.local/bin/raiplaysound-cli --version
```

Or run it directly from the project venv:

```bash
.venv/bin/python -m raiplaysound_cli --version
```

Alternative installs from Git:

```bash
pip install "git+https://github.com/<owner>/raiplaysound-cli.git"
pip install --user "git+https://github.com/<owner>/raiplaysound-cli.git"
pipx install "git+https://github.com/<owner>/raiplaysound-cli.git"
```

Uninstalling:

| Install method | Uninstall command |
| --- | --- |
| `make install` | `make uninstall` |
| `make install-dev` | `make uninstall-dev` |
| `pip install ...` | `pip uninstall raiplaysound-cli` |
| `pipx install ...` | `pipx uninstall raiplaysound-cli` |

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

## Quick Start

```bash
raiplaysound-cli list --stations
raiplaysound-cli list --programs
raiplaysound-cli list --episodes america7
raiplaysound-cli download america7
```

## Common Workflows

### Discover stations and programs

```bash
raiplaysound-cli list --stations
raiplaysound-cli list --programs
raiplaysound-cli list --programs --filter radio2
raiplaysound-cli list --stations --detailed
```

### Inspect seasons and episodes

```bash
raiplaysound-cli list seasons america7
raiplaysound-cli list episodes america7
raiplaysound-cli list episodes america7 --show-urls
raiplaysound-cli list seasons america7 --json
```

### Download episodes

```bash
raiplaysound-cli download [OPTIONS] <program_slug|program_url>
raiplaysound-cli download musicalbox
raiplaysound-cli download --format mp3 --jobs 5 musicalbox
raiplaysound-cli download --season 1,2 america7
raiplaysound-cli download --missing america7
```

### Download specific episode selections

```bash
raiplaysound-cli download --episode-ids <id1,id2> america7
raiplaysound-cli download --episode-url <episode-url> america7
```

### Generate RSS and playlists

```bash
raiplaysound-cli download --rss --playlist musicalbox
```

Command forms:

```bash
raiplaysound-cli download [OPTIONS] <program_slug|program_url>
raiplaysound-cli list [OPTIONS] stations|programs
raiplaysound-cli list [OPTIONS] seasons|episodes <program_slug|program_url>
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
make install
make install-dev
make uninstall
make run
make test
make lint
make lint-docs
```

Validation currently includes:

- `ruff check src tests`
- `mypy src tests`
- `black --check src tests`
- `python -m py_compile src/raiplaysound_cli/*.py`
- `pytest`
- `markdownlint`

## Disclaimer

RaiPlaySound CLI is an independent, community-developed project and is not
affiliated with, endorsed by, or officially connected with RAI, RaiPlaySound,
or the official RaiPlaySound application. "RAI", "RaiPlaySound", radio station
names, program names, and related marks remain the property of their
respective owners.
