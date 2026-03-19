# Program Grouping Audit

Live audit date: `2026-03-19`

This audit was generated from the current RaiPlaySound catalog and written to:

- `docs/audits/program-grouping-audit.csv`
- `docs/audits/program-grouping-audit.json`
- `docs/audits/program-grouping-summary.json`

The CSV and JSON files contain one entry for every program discovered in the
live catalog.

## Scope

- Programs audited: `1969`
- Programs with grouping filters: `314`
- Programs treated as flat: `1655`
- Grouped programs missed by the current grouping heuristic: `40`

That means the current logic misses about `12.7%` of grouped programs
(`40 / 314`), even though the grouping data is already present in the program
JSON payload.

## Main Findings

The current implementation is too dependent on hard-coded section names and URL
shapes.

It works well for familiar patterns such as:

- `episodi/.../stagione-N`
- `puntate/.../stagione-N`
- `speciali/...`
- `puntate-e-podcast/...`

It misses grouped programs when RaiPlaySound uses arbitrary section names or
product-specific routing, even if the JSON `filters` array is perfectly usable.

Observed miss classes in the live data include:

- custom season containers such as `raiplaysound-puntate-block`
- custom program-specific section names such as `futuradio`
- editorial buckets exposed under `clip`, `clip-`, `sezioni`, or similar
- year archives exposed under custom paths
- named collections such as `cicli`

## Radio2 a Fumetti

`radio2afumetti` is a confirmed live miss.

- Station: `radio2`
- Raw grouping mode: `cycle`
- Raw group count: `18`
- Raw section: `cicli`
- Current detection result: `0` groups

Example live labels:

- `Diabolik - Vampiri a Clerville`
- `Tex Willer - Mefisto`
- `Tex Willer - Ombre nella notte`
- `Dylan Dog - Necropolis`
- `Dylana Dog - L'uccisore di streghe`

The current code misses this program because `_classify_group()` does not know
the `cicli` section, so `list seasons radio2afumetti` falls back to the flat
path and never exposes the buckets.

## Distribution

The audit grouped programs into coarse live categories:

| Mode | Count |
| --- | ---: |
| `seasonal` | 128 |
| `bucket` | 81 |
| `mixed` | 42 |
| `year` | 33 |
| `other` | 25 |
| `series` | 3 |
| `special` | 1 |
| `cycle` | 1 |

The most common raw filter sections were:

| Section | Programs |
| --- | ---: |
| `puntate` | 139 |
| `episodi` | 107 |
| `raiplaysound-puntate-block` | 21 |
| `clip` | 6 |
| `puntate-e-podcast` | 5 |

The most common miss sections were:

| Section | Programs |
| --- | ---: |
| `raiplaysound-puntate-block` | 11 |
| `clip` | 6 |
| `a-spasso-con-radic-` | 1 |
| `podcast-` | 1 |
| `che-ci-faccio-qui-raiplaysound-puntate-block` | 1 |

## Viable Detection Strategy

Fast and future-proof detection should be based on `program.json["filters"]`
first, with HTML scraping only as a fallback.

Recommended approach:

1. Fetch `https://www.raiplaysound.it/programmi/<slug>.json` once.
2. If `filters` is empty, treat the program as flat unless separate season
   discovery proves otherwise.
3. If `filters` is present, treat each filter as a first-class grouping source.
4. Build the selector key from:
   - `filter.path` first
   - then the last URL segment from `filter.weblink`
   - then a normalized label fallback
5. Classify kind conservatively:
   - `season` if label or path clearly encodes a season
   - `special` if label or routing says `special`
   - `replica` if label or routing says `replica`
   - `year` if the grouping is an explicit year bucket
   - otherwise `group`
6. Preserve the raw section name as metadata, but do not require it to be known
   in advance.
7. Use the filter `weblink` as the source URL for grouped episode listing and
   downloading.
8. Keep the current HTML-based logic only as a fallback when `filters` is
   missing or malformed.

Why this is future-proof:

- RaiPlaySound can invent new section names without breaking detection.
- The CLI stops coupling grouping support to a hand-maintained allowlist.
- `filter.path` and `filter.weblink` are stable selector sources even when the
  human label changes.
- Unknown groupings still remain usable because they can fall back to generic
  `group` behavior instead of disappearing.

## Implementation Notes

The main code change should move grouping discovery from section-name pattern
matching to a filter-first model in `src/raiplaysound_cli/episodes.py`.

Expected behavior changes:

- `list seasons` should expose all filter-backed groupings, even for unknown
  section names.
- programs with filter-backed groups should not silently fall back to flat
  episode lists
- `--group` should use opaque selector keys derived from filter metadata, not
  only from known route conventions
- season-like filters under custom sections should still be usable with
  `--season` when the label clearly encodes season identity

## Suggested Test Cases

Add regression coverage for at least:

- `radio2afumetti` using `cicli`
- custom season sections such as `raiplaysound-puntate-block`
- editorial buckets under `clip`
- year buckets under custom sections
- mixed programs where one filter is `Speciali` and others are regular groups
