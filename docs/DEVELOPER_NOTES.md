# Developer Notes

This document captures the RaiPlaySound site structure assumptions used by
`raiplaysound-cli`, the current implementation strategy in the codebase, and
live findings verified during the session on March 19, 2026.

It is intended as a fast handoff document for new contributors and AI agents.

## Table of Contents

- [Purpose](#purpose)
- [Repository Architecture](#repository-architecture)
- [External Dependencies](#external-dependencies)
- [RaiPlaySound Data Sources](#raiplaysound-data-sources)
- [Current CLI Discovery Flow](#current-cli-discovery-flow)
- [Season URL Patterns Verified Live](#season-url-patterns-verified-live)
- [Season Detection Strategy](#season-detection-strategy)
- [Known Failure Modes](#known-failure-modes)
- [Caches and Output Artifacts](#caches-and-output-artifacts)
- [Key Commands for Contributors](#key-commands-for-contributors)
- [Suggested Next Work](#suggested-next-work)

## Purpose

The project provides a Python CLI, `raiplaysound-cli`, for:

- listing RaiPlaySound stations
- listing programs
- listing seasons and episodes for a specific program
- downloading episodes into `~/Music/RaiPlaySound/<slug>/`
- generating optional `feed.xml` and `playlist.m3u`

The design goal is pragmatic reliability against a site that exposes useful
information in multiple inconsistent shapes.

## Repository Architecture

The implementation is intentionally split into focused Python modules:

- [`src/raiplaysound_cli/cli.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/cli.py)
  is the main entrypoint and command dispatcher.
- [`src/raiplaysound_cli/config.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/config.py)
  parses `~/.raiplaysound-cli.conf` and builds `Settings`.
- [`src/raiplaysound_cli/catalog.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/catalog.py)
  handles station parsing, program catalog collection, and catalog cache I/O.
- [`src/raiplaysound_cli/episodes.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/episodes.py)
  resolves program slugs, discovers season/feed sources, enumerates episodes,
  and normalizes season and episode metadata.
- [`src/raiplaysound_cli/downloads.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/downloads.py)
  runs `yt-dlp`, parses progress, and manages archive cleanup for missing files.
- [`src/raiplaysound_cli/outputs.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/outputs.py)
  generates RSS and M3U outputs from local files and cached metadata.
- [`src/raiplaysound_cli/runtime.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/runtime.py)
  wraps HTTP requests, `yt-dlp` execution, and stale-lock recovery.

## External Dependencies

The CLI depends on external tools and external site behavior:

- `yt-dlp`
- `ffmpeg`
- live RaiPlaySound HTML and JSON responses

The implementation deliberately uses:

- direct HTTP GET for lightweight HTML and JSON fetches
- `yt-dlp` for playlist and metadata extraction

The project does not depend on an official stable RaiPlaySound API for all
operations.

## RaiPlaySound Data Sources

These are the main sources currently used by the application.

### Station listing

Source:

- `https://www.raiplaysound.it/dirette.json`

Used by:

- `parse_stations()` in
  [`catalog.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/catalog.py)

### Program catalog

Sources:

- `https://www.raiplaysound.it/sitemap.archivio.programmi.xml`
- `https://www.raiplaysound.it/programmi/<slug>.json`

Used by:

- `build_program_last_year_map()`
- `fetch_program_metadata()`
- `collect_program_catalog()`

Important note:

- program listing uses the cached full catalog plus local filtering by station
  slug rather than relying on station-scoped pages or station-scoped APIs

### Program pages

Source shape:

- `https://www.raiplaysound.it/programmi/<slug>`

Used for:

- detecting whether a program has seasons
- extracting season page links when present
- extracting season labels from visible page text

### Season pages

Verified live during this session:

- `https://www.raiplaysound.it/programmi/<slug>/episodi/stagione-<n>`
- `https://www.raiplaysound.it/programmi/<slug>/puntate/stagione-<n>`

These pages are not uniformly linked from the main program page.

### Other grouping pages

Verified live during this session:

- `https://www.raiplaysound.it/programmi/<slug>/speciali/<slug>`
- `https://www.raiplaysound.it/programmi/<slug>/puntate-e-podcast/<slug>`
- `https://www.raiplaysound.it/programmi/<slug>/puntate/<bucket>`
- `https://www.raiplaysound.it/programmi/<slug>/episodi-/<bucket>`

Observed bucket labels include:

- named thematic collections
- year buckets such as `2026`
- period buckets such as `2025-26` or `2021 (Gen-Giu)`

### Episode enumeration and metadata

The application uses `yt-dlp` against program pages and season pages:

- `--flat-playlist --print "%(id)s\t%(webpage_url)s"` for episode enumeration
- `--skip-download --print "%(id)s\t%(upload_date|NA)s\t%(title|NA)s\t%(season_number|NA)s"`
  for metadata collection

This is the main fallback when the HTML is inconsistent.

## Current CLI Discovery Flow

### `list stations`

- fetches `dirette.json`
- parses station slug, station name, page URL, and feed URL

### `list programs`

- reads the cached full program catalog when valid
- otherwise rebuilds it from sitemap plus per-program JSON

### `list episodes`

- resolves the slug or URL
- discovers grouped source pages from the main program page
- enumerates episodes with `yt-dlp`
- may refresh metadata cache when data is missing or stale
- suppresses fake season semantics for flat programs and non-season groupings
- accepts `--group` to select one or more discovered non-season groupings by
  key or normalized label

### `download`

- reuses the same grouping-aware source discovery used by episode listing
- accepts `--group` to select one or more discovered non-season groupings by
  key or normalized label
- writes into the target show directory
- preserves:
  - `.download-archive.txt`
  - `.metadata-cache.tsv`
  - optional `feed.xml`
  - optional `playlist.m3u`

### `list seasons`

This command was optimized during this session to avoid the heavy metadata path.

Current approach:

- resolve the slug
- discover group listing sources with `discover_group_listing_sources()`
- treat numbered seasons as one grouping family, but also surface non-season
  collections when the site exposes them
- enumerate episodes from the discovered grouping pages
- compute counts and year spans directly from episode URLs
- do not refresh metadata
- do not write `.metadata-cache.tsv`

This is faster than the full download-oriented context loader, but grouping
discovery still depends on the site exposing enough information in the HTML or
in probeable URLs.

## Season URL Patterns Verified Live

These findings were verified live on March 19, 2026.

### Pattern 1: `/episodi/stagione-N`

Example:

- `america7`

Observed behavior:

- the current site landing page linked `stagione-1`
- `stagione-2` still existed and was valid
- the landing page did not expose all seasons directly

Implication:

- season detection cannot assume the landing page lists every season

### Pattern 2: `/puntate/stagione-N`

Example:

- `leripetizioni`

Observed behavior:

- season links used `/puntate/stagione-N`, not `/episodi/stagione-N`
- the selected season appeared as plain text, for example `Stagione 5`
- older seasons appeared as links

Implication:

- season detection must support both `episodi` and `puntate`
- season detection cannot rely only on anchor tags, because the current season
  may be rendered as text rather than as a link

### Pattern 3: season selector without numbered season links

Example:

- `afroamerica-blackmusicrevolution`

Observed behavior:

- the page displayed `2^ Stagione`
- the initial HTML did not expose `.../stagione-N` links
- the visible link in the selector pointed to
  `/programmi/afroamerica-blackmusicrevolution/episodi/episodi`

Implication:

- there are programs with season state in the UI but without directly exposed
  numbered season paths in the initial HTML
- current discovery still under-detects seasons for this class of page

### Pattern 4: special collections instead of seasons

Example:

- `profili`

Observed behavior:

- the page exposes a selector for special collections such as
  `Speciale Pino Daniele` and `Speciale Lucio Dalla`
- collection URLs use `/programmi/<slug>/speciali/<speciale-slug>`
- the selected collection can map to the root program page, while alternates are
  exposed as links

Implication:

- not all grouped programs use seasons
- the CLI needs a grouping abstraction wider than numbered seasons

### Pattern 5: broader grouping families from live survey

The parallel survey also identified these families:

- year or period buckets under `puntate`, for example
  `/puntate/puntate-2025`
- hybrid season-year bucket slugs, for example
  `/puntate/stagione-2024-25`
- named subseries under `puntate-e-podcast`
- auxiliary content tabs such as `clip`, `extra`, `playlist`, and `novita`

Important distinction:

- auxiliary tabs are navigation surfaces, not season/group selectors
- named buckets and subseries are real groupings

## Season Detection Strategy

Current implementation in
[`episodes.py`](/Users/mmassari/Development/raiplaysound-cli/src/raiplaysound_cli/episodes.py):

1. Parse the main program page for season paths matching either:
   - `/programmi/<slug>/episodi/stagione-N`
   - `/programmi/<slug>/puntate/stagione-N`
2. Parse visible season labels such as `Stagione 5` to recover the currently
   selected season when it is text-only.
3. Parse broader grouping links for families such as:
   - `speciali`
   - `puntate-e-podcast`
   - named or year-based `puntate` buckets
4. Build candidate URLs for known season numbers under the detected section.
5. When only season labels are visible, probe verified candidate season URLs
   rather than assuming both `episodi` and `puntate` exist.
6. Probe consecutive season URLs above the highest known season number until no
   more pages are found.

This works for:

- `america7`
- `leripetizioni`
- `profili`

It does not yet fully work for:

- `afroamerica-blackmusicrevolution`

The discovery layer now finds more of the right URLs for this class of page,
but some of those pages can still fail later in `yt-dlp` extraction.

## Known Failure Modes

These are important for future contributors.

### The main program page is incomplete

The program landing page may not expose all valid season pages.

Example:

- `america7` exposed season 1 in HTML, but season 2 was still live and valid

### The current season may not be linked

The selected season may be rendered as plain text in a dropdown instead of a
link.

Example:

- `leripetizioni` showed `Stagione 5` as the selected text and linked only
  seasons 1 through 4

### Different section names are used

The site uses both:

- `episodi`
- `puntate`
- `speciali`
- `puntate-e-podcast`

Do not hardcode only one or assume only seasons exist.

### Some pages expose season UI without numbered season URLs

Example:

- `afroamerica-blackmusicrevolution`

The page shows a season selector, but the initial HTML does not expose any
`.../stagione-N` link. The CLI now probes verified season candidates for this
shape, but downstream extraction may still fail in `yt-dlp`.

### Some grouped pages are not seasons at all

Examples:

- `profili` uses `speciali`
- `3sullaluna` uses named thematic subseries
- some news and talk programs use year or period buckets

Implication:

- the internal discovery abstraction should be `groupings` or `collections`
  rather than only `seasons`
- the user-facing `list seasons` command currently acts as the grouping
  inspector for backwards compatibility

### Year span does not guarantee seasons

The program catalog year range can suggest a multi-season show, but it is not a
reliable substitute for explicit season discovery.

It is a useful heuristic for prioritizing investigation, not a correctness
signal.

## Caches and Output Artifacts

### Program catalog cache

Default path:

- `~/.local/state/raiplaysound-cli/program-catalog.tsv`

Contains tab-separated rows with:

- slug
- title
- station name
- station short slug
- year span

### Per-show metadata cache

Location:

- `~/Music/RaiPlaySound/<slug>/.metadata-cache.tsv`

Contains tab-separated rows with:

- episode ID
- upload date
- season
- title

Important note:

- after the optimization in this session, `list seasons` should not write this
  file

### Download archive

Location:

- `~/Music/RaiPlaySound/<slug>/.download-archive.txt`

Used by `yt-dlp --download-archive` for idempotent runs.

## Key Commands for Contributors

Environment setup:

```bash
make install-dev
```

Targeted tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_discovery.py
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_cli_entrypoints.py
```

Full validation:

```bash
make lint
```

Useful live smoke tests for discovery:

```bash
PYTHONPATH=src .venv/bin/python -m raiplaysound_cli list seasons america7
PYTHONPATH=src .venv/bin/python -m raiplaysound_cli list seasons leripetizioni
PYTHONPATH=src .venv/bin/python -m raiplaysound_cli list seasons profili
PYTHONPATH=src .venv/bin/python -m raiplaysound_cli list seasons afroamerica-blackmusicrevolution
```

Expected current status as of March 19, 2026:

- `america7` should show seasons 1 and 2
- `leripetizioni` should show seasons 1 through 5
- `profili` should show available `speciali`
- `afroamerica-blackmusicrevolution` is still a known gap

## Suggested Next Work

1. Handle program pages that expose season state but only link to generic pages
   such as `/episodi/episodi`.
2. Consider a dedicated cached season-summary artifact under the state
   directory, separate from download-side metadata cache.
3. Add more live regression examples to tests for season discovery edge cases.
4. If the site exposes embedded JSON for season selectors, prefer extracting
   season definitions from that data instead of relying only on links and label
   text.
