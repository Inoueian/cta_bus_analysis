# PID 6402 (148 Southbound) hand trim: four stops after Hubbard removed, Delaware to Hubbard median 7.37 min (measured 2026-10-02)

Tags: `kind:measurement source:bustracker source:mansueto topic:pattern-catalog topic:fixtures`

Migrated 2026-11-13 from vault `michigan-ave-6402-pattern-trim` (file dated 2026-10-02; TODO.md Done
dates the work 2026-10-03). It records a hand edit to one cached `getpatterns` response, why it was made
and what the pattern measured afterwards. The edit is not in the repo, which the migration confirmed
(see Corrections).

## Measurement

Bus Tracker lists PID 6402 as continuing down Michigan to Monroe, but published Mansueto trips on it are
seen at Delaware and never at Monroe. Four stop points (`typ == "S"`) after Michigan & Hubbard were
deleted from the owner's local `data/cta_api_cache/getpatterns_6402.json`; waypoints (`typ == "W"`) were
left alone.

| `stpid` | Stop removed |
|---|---|
| `1104` | Michigan & South Water |
| `1105` | Michigan & Lake/Randolph |
| `1106` | Michigan & Washington |
| `18396` | Michigan & Monroe |

`longest_corridor_run` on the edited pattern, then timing on the `last30d` parquet:

| Metric | Value |
|---|---|
| Entry | `1097` Michigan & Delaware |
| Exit | `1103` Michigan & Hubbard (Wrigley Bldg.) |
| Corridor stops | 7 |
| Trips | 479 |
| Median Delaware to Hubbard | 7.37 min |
| p25 / p75 | 6.45 / 8.41 min |
| Share under 5 min | about 9.8% |

## Facts confirmed

- With the trim the pattern passes the 5-minute rule (`DEFAULT_MIN_MEDIAN_MINUTES`) and was added to
  `notebooks/michigan_ave_kept_pids.json`, whose record for 6402 carries these numbers. Route 148 is kept
  on 6402 Southbound and 6403 Northbound.
- The 40-stop corridor snapshot and every other cached pattern were untouched.
- `cta.michigan_ave_segment.TRIM_6402_STPIDS` names the four stops; `segment_view_report` lists an
  issue if the legacy view has rows for PID 6402 at any of them.
- On Mansueto data the trim takes effect in the adapter: rows at a stop missing from the pattern are
  dropped as `stop_not_in_pattern` (`specs/mansueto-adapter.md`, Method).

## Corrections

- The trim lives only in a gitignored file on the owner's machine. Deleting that file, or working from
  a fresh clone, makes `batch_pattern_stops` refetch the untrimmed pattern. The committed fixture
  `tests/fixtures/getpatterns/getpatterns_6402.json` is the untrimmed pattern: it has all four stops
  (checked 2026-11-13). The entry and exit in `michigan_ave_kept_pids.json` still say Delaware to
  Hubbard, so code that reads the kept record is unaffected. Playbook gotcha "PID 6402's hand trim
  exists only in a local cache file".
- "last30d" is 2026-06-28 to 2026-07-28 (`docs/2026-11-04-mansueto-data-edge.md`).
- The vault note cited `michigan-ave-pattern-endpoint-coverage` for the original Monroe mismatch; that
  note is not in the repo. `build_endpoint_coverage_summary` in `cta.michigan_ave_segment` is the code
  that flags it (fewer than 50% of entry trips reaching the pattern exit).

## How to re-check

`cta.bustracker.load_getpatterns("6402")` and list the `typ == "S"` stops after `1103`: none means the
local cache is trimmed. `notebooks/michigan_ave_route_identification.ipynb` recomputes the timing. If CTA
changes the pattern so that buses do serve Monroe, drop the trim and re-run route identification.
