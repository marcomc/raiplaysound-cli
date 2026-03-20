# Command Behavior

This document describes the expected behavior of the user-facing
`raiplaysound-cli` commands as implemented in the current codebase.

It is intended as a command contract reference for contributors and AI agents.

## Table of Contents

- [Top-Level Invocation](#top-level-invocation)
- [Command Selection](#command-selection)
- [`list` Command](#list-command)
- [`download` Command](#download-command)
- [Config Interaction](#config-interaction)
- [Grouping and Season Behavior](#grouping-and-season-behavior)
- [Known Gaps](#known-gaps)

## Top-Level Invocation

- `raiplaysound-cli` with no arguments prints the focused top-level help text
  and exits with status `0`.
- `raiplaysound-cli --help` prints the same focused top-level help text and
  exits with status `0`.
- `raiplaysound-cli --version` prints the CLI version and exits with status
  `0`.
- Top-level help should list only the available commands and the pointer to
  command-specific help; it should not inline command examples or the full
  option sets for `list` and `download`.
- `raiplaysound-cli list --help` prints list-specific help with a compact usage
  line, grouped option sections, and short examples.
- `raiplaysound-cli download --help` prints download-specific help with grouped
  option sections, an explicit `PROGRAM_SLUG_OR_URL` positional name, and
  short examples.
- Compatibility aliases remain accepted where supported, but should be hidden
  from normal help output so the documented surface stays focused on the
  preferred flags.
- Empty invocation does not dispatch any config-selected command.

## Command Selection

Command resolution order is:

1. explicit `list` or `download` in argv
2. config key `COMMAND`
3. auto-detect `list` if list-specific switches are present
4. otherwise `download`

Important note:

- `--json` alone does not force `list`

Config loading order is:

1. `~/.raiplaysound-cli.conf`
2. `~/.raiplaysound-downloader.conf` only if the newer file is missing or empty

## `list` Command

`list` requires exactly one target.

Target forms:

- `stations`
- `programs`
- `seasons`
- `episodes`

Positional target forms are also supported, for example:

```bash
raiplaysound-cli list seasons america7
raiplaysound-cli list episodes america7
```

### `list stations`

- fetches live data from `dirette.json`
- does not use a live program cache for station discovery
- text output is a table with:
  - `Name`
  - `Programs`
  - `Slug`
  - `Page`
  - optional `Feed` with `--detailed`
- `--pager` can route text output through a pager without changing JSON output
- station program counts are taken from the locally cached program catalog when
  available; when no compatible local catalog exists yet, the count column may
  be unknown
- the footer prints a concrete `list programs --filter ...` example using one
  discovered station slug
- JSON output includes mode, count, detail flag, and station objects

### `list programs`

- uses the cached full program catalog when it is fresh and current
- otherwise rebuilds the catalog from the sitemap plus per-program JSON
- the default catalog cache age is intentionally long-lived: `2160` hours
  (90 days)
- this is separate from the per-show metadata cache, which defaults to `24`
  hours
- use `--refresh-catalog` to force a rebuild, or lower
  `--catalog-max-age-hours` / `CATALOG_MAX_AGE_HOURS` if you want fresher
  program listings
- station filtering is local, using the full cached catalog
- `--group-by auto` groups by station unless a station filter is active, in
  which case it groups alphabetically
- `--sorted` forces a flat alphabetical list
- text output is a table with:
  - `Name`
  - `Slug`
  - `Station`
  - `Years`
  - `Groupings`
  - `Description`
  - `Page`
- the `Groupings` column reflects the same discoverable grouping surfaces used
  by `list seasons`, including tab-based entries such as `Extra`, not just
  legacy `filters` metadata
- `--refresh-catalog` and `--catalog-max-age-hours` apply only to `list programs`
- `--pager` can route text output through a pager without changing JSON output
- the `Page` column is a clickable terminal link in Rich-capable terminals
- the footer prints concrete follow-up commands for:
  - listing programs for one station
  - listing episodes for one program
  - downloading one program
- errors if the station filter matches nothing

### `list seasons`

- requires a program slug or full program URL
- uses the lightweight grouping discovery path and should not refresh or write
  `.metadata-cache.tsv`
- text output is a table with:
  - `Program`
  - `Type`
  - `Name`
  - `Episodes`
  - `Selector`
  - `Published`
- when the program exposes real seasons, it prints seasons
- when the program exposes other grouping families, it prints groupings instead
  of incorrectly collapsing to a flat list
- repeated runs can reuse a dedicated state-dir summary cache instead of
  re-enumerating every grouping every time
- cached list payloads are short-lived and versioned, and stale or incompatible
  payloads must be rebuilt automatically rather than reused
- grouped output includes the exact selector token once in the table and keeps
  the download suggestions generic instead of printing one command per row
- `--season` narrows the output only for real seasonal programs
- `--season` is rejected for non-season grouped programs and flat programs
- JSON output exposes:
  - `has_seasons`
  - `has_groups`
  - `items`

### `list episodes`

- requires a program slug or full program URL
- aggregates episodes across discovered group pages when the program is grouped
- uses a read-only listing path: it reuses any existing `.metadata-cache.tsv`
  for enrichment, but it should not refresh or rewrite that cache
- repeated runs can reuse a list-only cache keyed by the resolved source set
- cached list payloads are short-lived and versioned, and stale or incompatible
  payloads must be rebuilt automatically rather than reused
- `--group` narrows grouped programs to one or more discovered grouping keys or
  labels
- `--group` cannot be combined with `--season`
- for real seasonal programs, it shows the season column
- for non-season grouped programs, it shows a grouping column instead
- for flat programs with no real seasons or groupings, it shows no grouping
  column at all and must not invent `S1`
- JSON output includes:
  - `group`
  - `group_kind`
  - `season`
  - `date`
  - `title`
  - `id`
  - `url`
- `--show-urls` adds the URL column in text mode
- by default, when seasons exist and no explicit episode or season filter is
  provided, it lists the latest season
- for flat programs, JSON output should use `season: null` rather than a
  synthetic season number

## `download` Command

- requires a program slug or full program URL, either on the command line or
  through config `INPUT`
- downloads into `TARGET_BASE/<slug>/`, defaulting to
  `~/Music/RaiPlaySound/<slug>/`
- uses:
  - `.metadata-cache.tsv`
  - `.download-archive.txt`
  - optional `feed.xml`
  - optional `playlist.m3u`
- reuses grouped-source discovery, so grouped programs download across the same
  discovered collections used by `list episodes`
- defers metadata refresh until after episode filtering, so narrow selections
  such as `--group`, `--episode-ids`, and `--episode-urls` only refresh
  metadata for the episodes that will actually be downloaded
- `--group` narrows grouped downloads to one or more discovered grouping keys
  or labels
- supports season filtering, episode-ID filtering, and episode-URL filtering
- supports legacy aliases:
  - `--seasons` for `--season`
  - `--episodes` for `--episode-ids`
- if `CLEAR_METADATA_CACHE` is enabled, it removes the metadata cache before
  rebuilding it
- if archive-marked files are missing locally and `AUTO_REDOWNLOAD_MISSING` is
  enabled, the CLI removes those IDs from the archive and re-downloads them
- if `AUTO_REDOWNLOAD_MISSING` is not enabled, it skips the archive/file
  existence scan entirely
- uses `JOBS` workers for source downloads, a separate internal `ffmpeg`
  conversion queue, and `CHECK_JOBS` workers for archive/file checks
- appends archive entries only after the conversion stage succeeds
- uses a recoverable `.run-lock` directory
- only supports these audio formats:
  - `mp3`
  - `m4a`
  - `aac`
  - `ogg`
  - `opus`
  - `flac`
  - `wav`
- returns `1` if any selected episode fails
- on success, can generate RSS and/or playlist output after downloads finish

## Config Interaction

The config file is plain `KEY=VALUE`.

Rules:

- blank lines and comments are ignored
- surrounding quotes are stripped
- `~` and `$HOME` are expanded for paths
- unknown keys are ignored
- invalid integer values raise a `CLIError`
- invalid booleans are ignored and leave defaults unchanged
- explicit CLI options override config defaults for the current run

Relevant config behavior:

- `INPUT` can supply the program for `download`, `list seasons`, and
  `list episodes`
- `LIST_TARGET` only applies when `list` is selected and no explicit list
  target was passed
- `GROUPS_ARG` acts as the default `--group` value for `download` and
  `list episodes`
- `STATION_FILTER`, `GROUP_BY`, `PODCASTS_SORTED`, `SHOW_URLS`,
  `STATIONS_DETAILED`, and `PAGER` act as list defaults
- `CHECK_JOBS`, `TARGET_BASE`, and `CATALOG_CACHE_FILE` are config-only knobs

## Grouping and Season Behavior

- season filters accept values `1` through `100` or `all`
- `list episodes` and `download` default to the latest season when real
  seasons exist and no explicit season or episode filter is provided
- season discovery supports both:
  - `/episodi/stagione-N`
  - `/puntate/stagione-N`
- current-season text without a link is handled for season discovery
- grouped programs can also use non-season families such as:
  - `speciali`
  - named thematic buckets
  - year or period buckets
- `list seasons` currently acts as the grouping inspector for backwards
  compatibility, and it should remain the stable long-term grouping inspector
  command name

## Known Gaps

- some program pages expose grouped UI state without directly exposing the full
  grouping set in the initial HTML, so discovery may need to rely on embedded
  program JSON filter definitions instead of only anchor tags
- some grouped pages can still fail downstream in `yt-dlp` extraction even when
  the HTML discovery layer finds the right season or grouping URLs
