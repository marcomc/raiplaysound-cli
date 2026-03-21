# List Seasons Validation Report

Validation date: `2026-03-20`

This report compares the current `raiplaysound-cli list seasons` discovery path against the grouped-program baseline in `docs/audits/program-grouping-audit.json`.

Baseline used:

- only grouped programs from the audit: `418`
- expected groups taken from each program entry's `raw_groups`
- current implementation under test: `discover_group_listing_sources()`

## Final Result

- Grouped programs checked: `418`
- Exact matches: `408`
- Final mismatches: `10`
- Remaining live request errors: `0`

## Retry Outcome

- Initial parallel-sweep live `403` errors: `82`
- Sequential retry recoveries: `81`
- Persistent request failures after retry: `0`

## Interpretation

- The sequential retry eliminated all persistent live request failures.
- The remaining differences are discovery over-reporting cases where the CLI surfaces an extra default root grouping such as `episodi` or `puntate` in addition to the audited custom grouping.
- No confirmed case remains where an audited grouping was missing from the current discovery output.

## Final Mismatch Slugs

- `fueddudemaistu`
  expected: `fueddu-de-maistu-ii` (group)
  actual: `episodi` (group), `fueddu-de-maistu-ii` (group)
- `kulturnidogodki-kulturneknjineinliterarnenovosti`
  expected: `intervjuji` (group)
  actual: `episodi` (group), `intervjuji` (group)
- `lapennicanza`
  expected: `clip` (group), `episodi` (group), `radio2-radio-show-la-pennicanza` (group)
  actual: `clip` (group), `episodi` (group), `puntate` (group), `radio2-radio-show-la-pennicanza` (group)
- `lasveglianza`
  expected: `radio2-radio-show-la-sveglianza` (group)
  actual: `puntate` (group), `radio2-radio-show-la-sveglianza` (group)
- `nativa`
  expected: `edizione-2021` (group)
  actual: `edizione-2021` (group), `episodi` (group)
- `senzaconfini`
  expected: `viaggiare-in-sicurezza-` (group)
  actual: `episodi` (group), `viaggiare-in-sicurezza-` (group)
- `vivarai2`
  expected: `i-stagione` (group)
  actual: `episodi` (group), `i-stagione` (group)
- `vivarai2vivasanremo`
  expected: `edizione-2023` (group)
  actual: `edizione-2023` (group), `puntate` (group)
- `zborovskaglasba`
  expected: `zborovski-utrip` (group)
  actual: `puntate` (group), `zborovski-utrip` (group)
- `biaxadorainsutempus`
  expected: `biaxadora-in-su-tempus-ii` (group)
  actual: `biaxadora-in-su-tempus-ii` (group), `puntate` (group)
