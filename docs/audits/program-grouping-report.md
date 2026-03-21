# Program Grouping Audit

Live audit date: `2026-03-20`

This audit was generated from the current RaiPlaySound catalog and written to:

- `docs/audits/program-grouping-audit.csv`
- `docs/audits/program-grouping-audit.json`
- `docs/audits/program-grouping-summary.json`

The CSV and JSON files contain one entry for every program discovered in the
live catalog sitemap.

## Scope

- Programs audited: `1969`
- Unreachable program JSON payloads: `0`
- Grouped programs: `418`
- Multi-group programs: `376`
- Flat programs: `1551`

The audit covers the full live RaiPlaySound program catalog exposed by
`https://www.raiplaysound.it/sitemap.archivio.programmi.xml`, not a station
sample.

## Main Findings

The earlier audit and report were too narrow because they treated
`program.json["filters"]` as the only discoverable grouping source.

Current developer notes and current application code both use two grouping
surfaces from `programmi/<slug>.json`:

- `filters`
- `tab_menu`

This matters because many live programs expose usable groupings only through
`tab_menu`, and some mixed programs need the root `Episodi` surface to coexist
with additional tab-backed groupings such as `Extra`, `Clip`, `Audiolibri`, or
`Playlist`.

The audit artifacts now preserve two views:

- `raw_groups`: strict payload-derived grouping surfaces from
  `discover_groups_from_program_payload()`
- `effective_groups`: the accepted live discovery view used by `list seasons`,
  which can also include redundant default root groupings such as `Episodi` or
  `Puntate`

This matters for the handful of programs where the live CLI intentionally shows
an extra default root grouping in addition to the stricter payload-derived
custom grouping.

## Distribution

Grouped programs by effective mode:

| Mode | Count |
| --- | ---: |
| `group` | 221 |
| `seasonal` | 121 |
| `mixed` | 53 |
| `year` | 23 |
| `flat` | 1551 |

Discovery-surface coverage:

| Surface metric | Count |
| --- | ---: |
| Programs with `filters` present | 314 |
| Programs with `tab_menu` present | 1928 |
| Grouped via `filters` | 313 |
| Grouped via `tab_menu` | 418 |
| Grouped via `tab_menu` only | 105 |
| Grouped via both `filters` and `tab_menu` | 313 |

Important nuance:

- `tab_menu` is present on most programs, but in many cases it only exposes the
  root `Episodi` surface.
- The meaningful grouped-program count is `418`, not `1928`.
- `10` grouped programs currently gain an extra accepted default root grouping
  in `effective_groups` compared with `raw_groups`.

The most common routed sections for discovered groups were:

| Section | Programs |
| --- | ---: |
| `puntate` | 139 |
| `episodi` | 106 |
| `raiplaysound-puntate-block` | 21 |
| `clip` | 6 |
| `puntate-e-podcast` | 5 |

## Radio2 a Fumetti

`radio2afumetti` remains a useful regression example, but it is no longer the
whole story.

- Station: `radio2`
- Effective discovery surface: `filters` plus `tab_menu`
- Effective grouping kind: generic `group`
- Discoverable group count: `18`
- Section examples: `cicli`

Example live labels:

- `Diabolik - Vampiri a Clerville`
- `Tex Willer - Mefisto`
- `Tex Willer - Ombre nella notte`
- `Dylan Dog - Necropolis`
- `Dylana Dog - L'uccisore di streghe`

This program originally exposed why hard-coded section allowlists were fragile.
Newly documented `tab_menu` cases show the same broader lesson: grouping
support must not depend on a closed set of known route names or on `filters`
alone.

## Tab-Menu-Only Cases

The refreshed audit finds `105` grouped programs that would be missed if the
CLI or reporting logic looked only at `filters`.

Representative live examples:

- `100voltealbertosordi`: `Episodi`, `Clip`
- `a3ilformatodellarte`: `Episodi`, `Clip`, `Extra`
- `adaltavoce`: `Episodi`, `Audiolibri`
- `aspettandovivarai2`: `Episodi`, `Extra`
- `fahrenheit`: `Episodi`, `Clip`, `Extra`

These are exactly the cases where the root `Episodi` tab must coexist with
additional tab-backed groupings.

## Viable Detection Strategy

Fast and future-proof detection should use the same grouping discovery surfaces
everywhere:

1. Fetch `https://www.raiplaysound.it/programmi/<slug>.json` once.
2. Inspect both `filters` and `tab_menu`.
3. Keep the active root `/programmi/<slug>` entry when non-root tabs also
   exist, because that root usually represents the main `Episodi` surface.
4. Treat any discoverable entry with a usable URL and selector key as a
   first-class grouping source.
5. Build selector keys from stable metadata:
   - route path first when available
   - otherwise the final URL segment
   - otherwise a normalized label
6. Classify kind conservatively:
   - `season` for clear season identities
   - `special` for specials
   - `replica` for replicas
   - `year` for explicit year buckets
   - otherwise generic `group`
7. Use the same discovery function for:
   - `list seasons`
   - `list episodes`
   - `download --group`
   - the `Groupings` column in `list programs`
8. Fall back to page-level enumeration only when a discoverable grouping page
   fails to enumerate through the usual playlist path.

Why this is future-proof:

- RaiPlaySound can introduce new route names without breaking discovery.
- `filters`-only and `tab_menu`-only programs are both covered.
- Mixed root-plus-tab layouts keep the main `Episodi` surface visible.
- Audit reporting and CLI behavior stay aligned because they reuse the same
  discovery logic.

## Suggested Regression Cases

Keep regression coverage for at least:

- `radio2afumetti` using `cicli`
- custom season sections such as `raiplaysound-puntate-block`
- tab-menu-only programs exposing `Extra`, `Clip`, or `Audiolibri`
- mixed programs where root `Episodi` must coexist with additional tab-backed
  groups
- mixed programs with `Speciali` plus other groups
