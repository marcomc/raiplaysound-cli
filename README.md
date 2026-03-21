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
- [Testing](#testing)
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
git clone https://github.com/marcomc/raiplaysound-cli.git
cd raiplaysound-cli
make install
```

This installs the package into:

- `~/.local/share/raiplaysound-cli/venv`

and creates the user-facing command at:

- `~/.local/bin/raiplaysound-cli`

Editable development install:

```bash
git clone https://github.com/marcomc/raiplaysound-cli.git
cd raiplaysound-cli
make install-dev
```

`make install-dev` keeps the command in `~/.local/bin/raiplaysound-cli`, but
points it at the project-local `.venv` so source edits take effect immediately.

Run the CLI from the user install:

```bash
~/.local/bin/raiplaysound-cli --version
```

Print the focused top-level command overview:

```bash
~/.local/bin/raiplaysound-cli
```

Use command-specific help for detailed options:

```bash
~/.local/bin/raiplaysound-cli list --help
~/.local/bin/raiplaysound-cli search --help
~/.local/bin/raiplaysound-cli download --help
```

The subcommand help screens are organized by topic and include short examples,
so they are the best place to discover the supported flags in practice.

Or run it directly from the project venv:

```bash
.venv/bin/python -m raiplaysound_cli --version
```

Alternative installs from Git:

```bash
pip install "git+https://github.com/marcomc/raiplaysound-cli.git"
pip install --user "git+https://github.com/marcomc/raiplaysound-cli.git"
pipx install "git+https://github.com/marcomc/raiplaysound-cli.git"
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
- Supports `list`, `search`, and `download` commands
- Lists stations, programs, seasons, and episodes
- Searches stations, programs, locally cached seasons/groupings, and locally
  cached episode metadata
- Downloads episodes into `~/Music/RaiPlaySound/<slug>/`
- Uses `yt-dlp --download-archive` for idempotent repeat runs
- Supports audio formats `mp3`, `m4a`, `aac`, `ogg`, `opus`, `flac`, and `wav`
- Supports season filtering, episode ID filtering, and episode URL filtering
- Supports automatic re-download of archive-marked but missing local files
- Generates Rich-based live per-episode download progress with megabyte size
  tracking and aggregate transfer speed
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

Cache-age defaults are intentionally different:

- `METADATA_MAX_AGE_HOURS` defaults to `24` for per-show episode metadata
- `CATALOG_MAX_AGE_HOURS` defaults to `2160` (90 days) for the full program
  catalog used by `list programs`

If you want fresher program listings by default, lower
`CATALOG_MAX_AGE_HOURS` in your config, for example:

```bash
CATALOG_MAX_AGE_HOURS=24
```

Supported config keys:

| Config key | CLI option | Scope |
| --- | --- | --- |
| `AUDIO_FORMAT` | `--format` | download |
| `JOBS` | `--jobs` | download |
| `SEASONS_ARG` | `--season` | download, list `episodes` |
| `GROUPS_ARG` | `--group` | download, list `episodes` |
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
| `GROUP_BY` | `--group-by` | list `programs` |
| `PODCASTS_SORTED` | `--sorted` | list `programs` |
| `STATION_FILTER` | `--filter` | list `programs` |
| `FORCE_REFRESH_CATALOG` | `--refresh-catalog` | list `programs` |
| `CATALOG_MAX_AGE_HOURS` | `--catalog-max-age-hours` | list `programs` |
| `STATIONS_DETAILED` | `--detailed` | list `stations` |
| `SHOW_URLS` | `--show-urls` | list `episodes`, search |
| `PAGER` | `--pager` | list, search |
| `INPUT` | `<program_slug\|program_url>` | download, list `seasons`, list `episodes` |

`FORCE_REFRESH_CATALOG` and `CATALOG_MAX_AGE_HOURS` affect only `list programs`.
They do not change the per-show metadata cache used by `download` and
`list episodes`.

`RSS_BASE_URL` must be a direct file-serving base URL. The CLI builds enclosure
URLs as:

```text
<RSS_BASE_URL>/<program_slug>/<filename>
```

That means ordinary browser share-page URLs with query strings are not valid
RSS enclosure bases.

## Usage

## Quick Start

```bash
raiplaysound-cli list stations
raiplaysound-cli list programs
raiplaysound-cli search lucio dalla
raiplaysound-cli list episodes america7
raiplaysound-cli download america7
```

## Common Workflows

### Discover stations and programs

```bash
raiplaysound-cli list stations
raiplaysound-cli list programs
raiplaysound-cli list programs --filter radio2
raiplaysound-cli list stations --detailed
```

Example output:

```text
Available RaiPlaySound radio stations (7):
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━┓
┃ Name          ┃ Programs ┃ Slug         ┃ Page ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━┩
│ Rai Radio 1   │      123 │ radio1       │ open │
│ Rai Radio 2   │      107 │ radio2       │ open │
│ Rai Radio 3   │      198 │ radio3       │ open │
└───────────────┴──────────┴──────────────┴──────┘

Next:
  programs for one station: raiplaysound-cli list programs --filter radio2
```

```text
Programs grouped alphabetically (107):
┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ Name                 ┃ Slug          ┃ Station ┃ Years     ┃ Groupings ┃ Description                  ┃ Page ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ 1 M Next             │ 1mnext        │ radio2  │ 2025      │         — │ —                            │ open │
│ 100 Volte Alberto    │ 100voltealbe… │ radio2  │ 2020-2025 │         — │ —                            │ open │
│ Sordi                │               │         │           │           │                              │      │
│ A qualcuno piace     │ aqualcunopia… │ radio2  │ 2025-2026 │         2 │ Un programma del mattino... │ open │
│ Radio2               │               │         │           │           │                              │      │
└──────────────────────┴───────────────┴─────────┴───────────┴───────────┴──────────────────────────────┴──────┘

Next:
  one station:   raiplaysound-cli list programs --filter radio2
  one program:   raiplaysound-cli list episodes 1mnext
  download one:  raiplaysound-cli download 1mnext
```

`list programs` intentionally prints the full table by default so the output is
pipe-friendly and easy to capture. For large catalogs, the most practical ways
to narrow or browse the output are `--filter`, `--sorted`, or the opt-in
`--pager` flag rather than auto-paging by default.

### Search cached metadata

```bash
raiplaysound-cli search lucio
raiplaysound-cli search burnt sugar --json
raiplaysound-cli search radio2 --show-urls
```

`search` always queries live stations and the cached-or-refreshed global
program catalog. Season/grouping and episode matches come from local caches
that were already populated by earlier `list` or `download` runs.

If RaiPlaySound is temporarily unavailable, `search` still returns any local
season/grouping and episode matches it can find from existing caches instead
of failing outright. Live station and program sections are left empty in that
case, and the cache summary notes the live lookup failure.

That means:

- station and program matches are available immediately
- season/grouping matches depend on cached `list seasons` payloads
- episode matches depend on local `.metadata-cache.tsv` files and, when
  available, cached `list episodes` payloads

When episode metadata is refreshed through downloads, the per-show
`.metadata-cache.tsv` now also stores a searchable text field derived from the
episode JSON payload. That lets `search` match titles, authors, descriptions,
and other metadata strings that Rai exposes for the cached episode.

### Inspect seasons and episodes

```bash
raiplaysound-cli list seasons america7
raiplaysound-cli list episodes america7
raiplaysound-cli list episodes america7 --show-urls
raiplaysound-cli list seasons america7 --json
raiplaysound-cli list episodes battiti --group speciali
```

Season listing uses a lightweight discovery path, so `list seasons` avoids
download-side metadata refreshes and is typically faster than episode
inspection or download preparation.

Repeated `list seasons <program>` runs now also use a dedicated list-summary
cache under the state directory, separate from download-side metadata, so
grouped programs do not need to re-enumerate every grouping on every call.

For programs that use non-season groupings on RaiPlaySound, `list seasons`
also reports those groupings instead of incorrectly collapsing everything into a
flat episode list. For example, programs may expose specials, named thematic
collections, or year and period buckets instead of numbered seasons.

Grouping discovery is now filter-first: when RaiPlaySound exposes selector
filters in the program JSON, the CLI treats those filters as the authoritative
group source even if the site uses custom route names such as `cicli`,
`clip`, or other product-specific paths.

`list seasons` is also the long-term grouping inspector name for the CLI, even
when the discovered program structure uses non-season collections.

When a program exposes real seasons, `list seasons <program> --season <n>` narrows the
output to the requested season. For non-season groupings or flat programs,
`--season` is rejected instead of being silently ignored.

Season selectors can be ordinary season numbers or year-style season keys such
as `2025` when RaiPlaySound models seasons that way.

`list episodes <program>` also aggregates episodes across discovered
groupings for grouped programs, instead of only listing the currently selected
subpage.

Episode listing now uses a read-only path: it can reuse an existing
`.metadata-cache.tsv` to improve titles and dates, but it does not refresh or
rewrite that cache during `list episodes`.

Repeated `list episodes` runs also use a list-only cache keyed by the resolved
source scope, so repeated calls for the same program or grouping can reuse the
previous listing without touching download artifacts.

Those list-only caches are versioned, and stale or incompatible cached payloads
are rebuilt automatically instead of being reused indefinitely.

When a program uses non-season groupings, `list episodes <program> --group <key>`
narrows the output to one or more discovered grouping keys or labels. For
example:

```bash
raiplaysound-cli list episodes battiti --group speciali
raiplaysound-cli list episodes profili --group speciale-lucio-dalla
```

`--group` cannot be combined with `--season`.

`list seasons <program>` now renders seasons and non-season groupings in a
table with:

- `Program`
- `Type`
- `Name`
- `Episodes`
- `Selector`
- `Published`

For grouped programs, the footer now shows compact generic `download --group`
examples instead of repeating one command per discovered grouping.

For flat programs that do not expose real seasons or other groupings,
`list episodes` does not invent a fake `S1` column. Those programs are shown
as a plain episode list, and JSON output reports the season as `null`.

`download <program>` now follows the same grouping-aware discovery path as
`list episodes`, so grouped programs can be downloaded across their
discovered collections instead of only the root subpage.

Download startup is also narrower now: episode discovery still happens across
the selected program or grouping, but metadata refresh is deferred until after
episode filtering. When you use selectors like `--group`, `--episode-ids`, or
`--episode-urls`, the CLI refreshes metadata only for the episodes that will
actually be downloaded.

During that preparation phase, the CLI now prints explicit startup steps such
as source discovery, episode enumeration, metadata refresh, and archive-file
checks so long grouped downloads are not silent before transfer starts.

Once transfers begin, each per-episode progress row now shows downloaded size
in megabytes, for example `5.0/10.0 MB`, while the overall row shows aggregate
transfer speed.

Download workers are now split into two stages:

- `yt-dlp` workers fetch source audio plus sidecar metadata and thumbnails into
  a hidden per-run workspace
- a separate `ffmpeg` queue converts those completed downloads into the final
  requested audio format and appends the archive entry only after conversion
  succeeds

That means long local conversion or thumbnail-embedding work no longer blocks
the next network download from starting as soon as a download worker becomes
free.

The staged conversion path also preserves richer embedded tags for seasonal
shows by restoring episode titles plus season and episode numbering from the
downloaded sidecar metadata.

When `--missing` is not enabled, the CLI now skips the archive/file existence
scan entirely instead of paying that startup cost on every download.

Example output:

```text
Available seasons for america7 (https://www.raiplaysound.it/programmi/america7):
  - Season 1: 71 episodes (published: 2023-2025)
  - Season 2: 17 episodes (published: 2025-2026)
```

```text
Episodes for america7 (https://www.raiplaysound.it/programmi/america7):
┏━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Season ┃ Date       ┃ Episode          ┃ ID               ┃ URL              ┃
┡━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ S2     │ 2026-03-13 │ America7 S2E17   │ 692674e0-ceb7-4… │ https://www.rai… │
│        │            │ La prima guerra  │                  │                  │
│        │            │ A.I.             │                  │                  │
│ S2     │ 2026-03-06 │ America7 S2E16   │ 7e2a8652-b220-4… │ https://www.rai… │
```

### Download episodes

```bash
raiplaysound-cli download [OPTIONS] <program_slug|program_url>
raiplaysound-cli download musicalbox
raiplaysound-cli download --format mp3 --jobs 5 musicalbox
raiplaysound-cli download --season 1,2 america7
raiplaysound-cli download battiti --group speciali
raiplaysound-cli download --missing america7
```

Example completion summary:

```text
Completed: done=1, skipped=0, errors=0
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
raiplaysound-cli list <stations|programs> [OPTIONS]
raiplaysound-cli list <seasons|episodes> [OPTIONS] <program_slug|program_url>
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

## Testing

See [`docs/TESTING.md`](/Users/mmassari/Development/raiplaysound-cli/docs/TESTING.md)
for the full validation and regression-test guide for users and AI agents.

## Disclaimer

RaiPlaySound CLI is an independent, community-developed project and is not
affiliated with, endorsed by, or officially connected with RAI, RaiPlaySound,
or the official RaiPlaySound application. "RAI", "RaiPlaySound", radio station
names, program names, and related marks remain the property of their
respective owners.
