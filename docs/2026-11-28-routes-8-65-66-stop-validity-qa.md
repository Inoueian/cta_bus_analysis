# Stop validity in the Mansueto view for routes 8, 65 and 66: 1,850,766 rows leave the 71.5M, the unwindowed build equals the 2026-11-15 QA (measured 2026-11-28)

Tags: `kind:qa source:mansueto stage:view topic:qa-table topic:pattern-catalog`

QA record for `specs/mansueto-stop-validity.md`: the Mansueto adapter's `pattern_join` now drops arrivals dated before a
stop's reviewed `valid_from` (`stop_before_valid_from`), arrivals inside a dated interval (`stop_not_served`) and one
unobserved run (`run_unobserved`), from the committed `notebooks/routes_8_65_66_stop_validity.json` (ADR-011, ADR-014,
ADR-015). It compares a full-history rebuild with the 2026-11-15 note (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`).
No threshold changed; the windows are the owner's reviewed ones.

## Measurement

```
python scripts/route_run_level.py --source mansueto --fetch --out-dir data/rrl_windowed      # 41 parquets (2.0 GB), 0 live getpatterns calls
python scripts/route_run_level.py --source mansueto --no-validity --out-dir data/rrl_unwindowed
```

Both builds read the same 24 pids from the committed getpatterns files (copied into `data/cta_api_cache/`, gitignored)
and the same parquets. Per-entry effects come from the unwindowed view under `data/rrl_unwindowed/source=mansueto`.

Per route, stage `pattern_join` (a reason not shown is 0; rows out of the whole build in the last column):

| Route | `stop_not_in_pattern` | `run_unobserved` | `stop_before_valid_from` | `stop_not_served` | View rows, unwindowed to windowed |
|---|---|---|---|---|---|
| 8 | 1,441,267 (was 1,441,269) | 108 | 538,940 | 10,289 | 29,586,573 to 29,037,238 |
| 65 | 48,621 | 0 | 0 | 0 | 13,085,453 to 13,085,453 |
| 66 | 1,775,939 | 0 | 1,301,431 | 0 | 28,852,161 to 27,550,730 |
| all | 3,265,827 | 108 | 1,840,371 | 10,289 | 71,524,187 to 69,673,421 |

- **The unwindowed build equals the 2026-11-15 note** row for row: 71,524,187 rows out, 3,265,829 `stop_not_in_pattern`,
  and the four per-pid counts of arrivals before today's geometry (636,909; 884,215; 354,954; 251,013).
- **Rows leaving: 1,850,766** = 1,840,371 + 10,289 + 108 − 2. The 2 are rows of the unobserved run that were
  `stop_not_in_pattern` in the unwindowed build; `run_unobserved` comes first and takes the whole run.
- **Route 65 has no change**, as specified.
- **Runs whose `run_id` has no trailing date: 0** in both builds (the date rule is the run id's).

## Per dominant pattern

`arrivals_before_today_geometry` is the build's own count (`detour_stop_arrivals.csv`: arrivals at stops first seen more
than 45 days after the pid's first, before the pid's last geometry change); the windows leave what is still served.

| Pid | Unwindowed (the 2026-11-15 note) | Windowed | `stop_before_valid_from` | `stop_not_served` | `run_unobserved` |
|---|---|---|---|---|---|
| 6662 (66 east) | 636,909 | 115,797 | 522,489 | 0 | 0 |
| 6665 (66 west) | 884,215 | 188,921 | 695,294 | 0 | 0 |
| 9368 (8 south) | 354,954 | 89,798 | 265,148 | 0 | 108 |
| 9376 (8 north) | 251,013 | 32,872 | 209,177 | 8,964 | 0 |

What the windowed counts still hold are arrivals the buses served: stops with no window (stop-id swaps `18720` and `18721`
on 6662, `18794` and `18802` on 6665, `5782` and `18786` on 9368, 44,368 to 68,017 each), 6665's six stops valid from
2025-09-28 (8,717 each before 2025-11-23), the days the review moved a date earlier (117 per stop on 6665, 177 on 9368),
and `15341` on 9376 before 2025-08-17 (32,872). The window key is (`route`, `direction`, `stop_id`) with every pattern of
the direction pooled (ADR-011), so the other pids of a direction lose arrivals at the same stops: route 66 83,648
(pids 4355, 4357, 6658, 6661), route 8 64,615 and 1,325 `stop_not_served` (pids 9250, 9343, 9345, 10949, 10951, 10954).

## What the review moved

Arrivals in the days between the measured window and the reviewed one, per entry (unwindowed view, the entry's own pid):

| Pid | Stops | Rule | Measured to reviewed | Arrivals per stop | Total | Effect against the measured window |
|---|---|---|---|---|---|---|
| 6662 | 8 | point 1 | 2025-09-27 to 2025-09-28 | 153 | 1,224 | dropped, not kept |
| 6662 | `6714` Orleans & Chicago | point 3 | none to 2025-09-28 | 58,055 | 58,055 | dropped, not kept |
| 6665 | 4 | point 1 | 2025-11-24 to 2025-11-23 | 117 | 468 | kept, not dropped |
| 6665 | `18803` Wells & Chicago | point 3 | none to 2025-11-23 | 67,899 | 67,899 | dropped, not kept |
| 9368 | 6 | point 1 | 2025-11-25 to 2025-11-23 | 178 | 1,068 | kept, not dropped |
| 9376 | `15341` | point 3 | `not_served` 2025-08-17 to 2025-11-22 | 8,964 | 8,964 | dropped, not kept |

The 18 date moves change 2,760 arrivals; the three added windows and the interval change 134,918. The dropped run
(vehicle 1286, 9368, 2025-11-24, earliest arrival 18:18 Chicago) has 108 rows in the build: 106 view rows and 2
that were `stop_not_in_pattern`.

## Corrections to earlier notes

- `specs/mansueto-stop-validity.md` estimated about 4,000 `stop_before_valid_from` and about 270 `stop_not_served` on the
  2025-10-14 fixture; measured 2,191 (route 8 1,338, route 66 853) and 118. The test pins the measured values.
- `docs/2026-11-15-routes-8-65-66-run-level-qa.md`: its 2,127,091 arrivals are the unwindowed count and stay true of an
  unwindowed build; the windowed view has 427,388 of them left, all at stops the buses served (above).

## How to re-check

`python scripts/route_run_level.py --source mansueto --no-validity` must reproduce the 2026-11-15 numbers; without
`--no-validity` it must reproduce the table above. A moved total is a behaviour change: a new window, a changed review
date or a new dropped run in the JSON, or a changed pattern in the getpatterns cache. `python scripts/qa.py` covers the
fixture day (`mansueto_2025_10_14_routes8_65_66`).
