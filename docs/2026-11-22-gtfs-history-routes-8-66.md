# Archived CTA GTFS for routes 8 and 66: each version is a dated `getpatterns`, and it dates every detour stop (measured 2026-11-22)

Tags: `kind:measurement source:gtfs source:bustracker topic:pattern-catalog topic:identifiers`

Contains data from [Transitland](https://www.transit.land/terms): the feed versions read here come from the Transitland
Feed Archive (ADR-013).

The TODO item "Historical pattern geometry from GTFS, feasibility for routes 8 and 66" was blocked on archive access;
the owner's Hobbyist/Academic access came through on 2026-11-22. This note answers the item's four checks and extends
the fourth to all 38 rows of the committed stop-validity windows (`notebooks/routes_8_65_66_stop_validity.json`). The
answer is yes: an archived version gives the stop ids and `pdist` that `getpatterns` would have served on its dates. No
view, threshold or window changes here. Notebook: `notebooks/gtfs_history_routes_8_66.ipynb` (Findings cell). It
follows `docs/2026-11-21-gtfs-history-access.md`.

## Measurement

22 versions of feed `f-dp3-cta`, one for each service day from 2024-07-08 to 2026-12-31, cached under
`data/gtfs/feed_versions/<sha1>.zip` (1.6 GB) with each file's SHA-1 checked against the version id. 21 came from
Transitland in 25 download requests (four extra: two probes, one connection reset, one wrong path), against the plan's
500 a month. Today's (`64cb6b84…`) came from CTA's site and is byte-identical to Transitland's latest. The download
endpoint answers 302 to a signed URL on `transitland.blob.core.windows.net`. That host was added to the cloud
environment's allowed hosts on 2026-11-22.

| Fetched | Service dates | sha1 | Read for |
|---|---|---|---|
| 2024-07-11 | 2024-07-08 to 2024-09-30 | `1df549a1b0b7cfbe74b3546e84635515646e0136` | checks 1 and 2 |
| 2024-08-22 | 2024-08-16 to 2024-10-31 | `d47ed8a7372487e24c13430982a01552d2070a98` | in force on 2024-09-03 |
| 2024-09-27 | 2024-09-24 to 2024-11-30 | `172bf32d7bfa0d81e93585f44edd87282004f936` | coverage |
| 2024-10-17 | 2024-10-14 to 2024-12-31 | `f226158db362bf1039034aba6114420e92da3241` | coverage |
| 2025-03-12 | 2024-12-16 to 2025-03-31 | `bb7910bb50ca31347df9420b6426cdd0517aab07` | coverage |
| 2025-03-18 | 2025-03-13 to 2025-05-31 | `0395f1ec8d38f509880530e3f6035efa3e6709ac` | coverage |
| 2025-04-30 | 2025-04-28 to 2025-06-30 | `1b4de7d5af5b9e71ea0169468ec10b3b1e3b1635` | coverage |
| 2025-06-10 to 2026-01-08 | | the ten versions of the 2026-11-21 note | around the 2025 detours |
| 2026-03-26 | 2026-03-20 to 2026-05-31 | `3fdb2739c597979bd0622b776496cb467d6bd3f4` | coverage |
| 2026-05-30 | 2026-05-28 to 2026-07-31 | `81c806bbfb678eb3e3a8292a0a83f768bdb1009d` | coverage |
| 2026-07-10 | 2026-07-07 to 2026-09-30 | `686b063b58e61693d948d8fcc8b12ee6a3313902` | coverage |
| 2026-09-16 | 2026-09-11 to 2026-11-30 | `5e71fa8fce816d00887722920f70d53c438d5686` | coverage |
| 2026-11-11 | 2026-10-29 to 2026-12-31 | `64cb6b84288a34196e3b7edf5ac5e79b5dfe1b7d` | calibration |

A pattern is a trip's ordered `(stop_id, shape_dist_traveled)` list from `stop_times.txt`. Every trip of a shape had
the same one, and no `calendar_dates.txt` addition fell outside a shape's calendar span. As in Mansueto's method
(ADR-009), each version is used from its first calendar day to the day before the next version's. Within it, the day
belongs to the schedule generation whose calendar covers it.

**Calibration on today's feed.** `stop_times.shape_dist_traveled` against the committed `getpatterns` fixtures:

| Pid | getpatterns stops | In GTFS | Largest difference |
|---|---|---|---|
| 9368, 9376 | 107, 104 | 106, 102 (no `18871`; no `18872`, `5888`) | 0 ft |
| 6662, 6665, 6656, 6657 | 69, 70, 76, 76 | all | 0 ft |

**Check 2.** Pings of the four pids projected onto their GTFS shape, `pdist` minus the distance along the shape, in
feet, pings within 200 ft of the shape:

| Day, version | Pings on the shape | Median | 5th to 95th percentile | 99% within | Per-stop median, largest |
|---|---|---|---|---|---|
| 2024-07-16, mid-2024 | 1,820 to 1,848 per pid | −46 to −62 | −88 to 0 | 72 to 94 | 68 to 91 |
| 2026-09-15, today's | 2,107 to 2,653 per pid | −44 to −51 | −93 to 3 | 71 to 112 | 66 to 79 |

**Check 3.** First day of each geometry change in the schedule against the raw pings (`geometry_changes` of
`notebooks/routes_8_65_66_pids.json`):

| Pattern | Pings: first day new | GTFS: first day (all Sundays) | GTFS minus pings | First carried by the version fetched |
|---|---|---|---|---|
| 8 north (9376), 8 south (9368) | 2025-08-17 | 2025-08-17 | 0, 0 | 2025-08-14 |
| 66 east (6662) | 2025-09-27 | 2025-09-28 | +1 | 2025-09-25 |
| 66 west (6665) | 2025-09-28 | 2025-09-28 | 0 | 2025-09-25 |
| 8 north (9376) | 2025-11-23 | 2025-11-23 | 0 | 2025-11-20 |
| 66 west (6665) | 2025-11-24 | 2025-11-23 | −1 | 2025-11-20 |
| 8 south (9368) | 2025-11-25 | 2025-11-23 | −2 | 2025-11-20 |

**Check 4, all 38 committed windows.** A stop id's days in its pid's GTFS pattern from 2024-09-03 to 2026-07-27,
against `valid_from`. Where they differ, the pattern on the uncovered days was searched for a stop with the same
street names:

| Verdict | Rows | Which |
|---|---|---|
| agrees | 12 | 6662 `18720`, `18721`; 6665's five Grand and Milwaukee stops from 2025-09-28; 9376's five from 2025-11-23 |
| same change, one or two days apart | 18 | 6662's eight (GTFS 2025-09-28, window 09-27); 6665 `6613`, `6614`, `5020`, `769` (GTFS 2025-11-23, window 11-24); 9368's six (GTFS 2025-11-23, window 11-25) |
| id changed at a corner the pattern served under another id | 5 | 9368 `18786` (`5790` before 2025-08-17; absent 2025-11-23 to 12-20, when `5502` stood in); 9368 `5782` (`15273`, then `17184`, before 2025-11-23); 6665 `18794` (`617` before 2025-09-28); 6665 `18802` (`620` before 2025-11-23); 6665 `771` (`18793`, 86 ft, 2025-09-28 to 11-22) |
| a period when the corner had no stop | 3 | 6662 `6714` Orleans & Chicago before 2025-09-28 (nearest 317 ft); 6665 `18803` Wells & Chicago before 2025-11-23 (nearest 383 to 385 ft); 9376 `15341` from 2025-08-17 to 2025-11-22 (nearest 440 ft; `15274` before) |

## Facts confirmed

- **An archived version is a dated `getpatterns`.** GTFS `stop_id` is `stpid` and `stop_times.shape_dist_traveled` is
  `pdist` in feet, exactly, today. On 2024-07-16 the mid-2024 version agrees with the pings as closely as today's feed
  does with today's pings. The ~50 ft that `pdist` falls short of the along-shape position is on both days, so it
  belongs to the pings, not the feed.
- **The pid is `shape_id % 100,000` in every version.** The three-digit prefix changes with each schedule generation:
  664 in mid-2024, 674 from 2025-08-17, 682 today.
- **Most versions carry two schedule generations.** Each has its own shape id per pid and its own calendar, and a
  geometry change is the day a generation starts. Here those days were all Sundays.
- **Check 1 holds.** The mid-2024 9368 pattern holds `15273`, `16125`, `15347`, `5788`, `5790`, and 9376's holds
  `15274`, `15363`, `5941`, `15405`, with their distances. 9368's pattern was 74,735 ft (14.15 mi), and the longest
  ping on 2024-07-16 was 14.14 mi.
- **Check 3: the schedule and Bus Tracker changed together, three days after publication.** Route 8's buses left
  Halsted on 2025-08-04 (EDA), so both trailed that detour by 13 days. Route 66 changed the day before the Chicago
  Avenue bridge closed (2025-09-29). Route 66 also lost its Chicago & Halsted stops on 2025-08-17, with route 8's
  detour: 6662 `565`, `566`; 6665 `612`, `613`.
- **Check 4.** Wells & Chicago (`18803`) enters 6665's pattern on 2025-11-23, and no 6665 stop stood at that corner
  before. `15341` enters 9376's pattern on 2025-11-23; before 2025-08-17 the corner was served as `15274`, and from
  2025-08-17 to 2025-11-22 by no stop. `18786` enters 9368's pattern on 2025-08-17 (`5790` before). The TODO item
  counted what a "not served" reading would drop on the dominant patterns. At Wells & Chicago it is 68,016 of
  106,256 arrivals. At `15341` on 9376 it is 41,836 of 64,228, and at `18786` on 9368 34,563 of 67,328. Those counts
  were not re-measured here.
- **The schedule did not change on 2024-09-03**, the day Mansueto's stop lists switched. The Chicago & Menard and
  Waller id swap (6662 `512`, `513` → `18720`, `18721`) was in the schedule by 2024-08-16, and the detour stops
  arrived only in 2025.
- **`shapes.txt` distances can be wrong while `stop_times.txt` distances are right.** In 9 of the 22 versions, 9376's
  shape runs 15,864 to 15,896 ft past its last stop: a constant jump near the start, on points identical to the next
  version's. Route 8's short patterns (9343 to 9345) always end 3,688 to 3,756 ft past theirs, and 10949, 10951,
  10954 and 8417 end 13,585 to 41,293 ft past theirs.
- **Today's GTFS and `getpatterns` disagree at Halsted & 56th and 57th.** GTFS held `5838` (9368), `5889` and `17400`
  (9376) to 2026-09-19 and has had no stop there since. `getpatterns` serves `18871`, `18872` and `5888`, which no
  version read holds. GTFS also dropped 2300 S Halsted (`5812`, `5918`) on 2026-07-12. Those five ids are not in
  today's `getpatterns`, so any Mansueto arrivals under them are dropped as `stop_not_in_pattern`.

## Corrections to earlier notes

- `docs/2026-11-21-gtfs-history-access.md`: "`shape_id` minus 68,200,000 is the Bus Tracker `pid`" holds only for
  today's prefix (682). Across versions, the pid is `shape_id % 100,000`. Its "versions valid from 2025-08-12,
  2025-09-24 and 2025-11-19 ... three to six days before each geometry change" is now measured: those versions carry
  the changes, each in a schedule generation starting on the change day, and their fetch dates are three days ahead.
- `docs/2026-11-21-stop-validity-windows.md` read Wells & Chicago as served on the old route (a corner stop); the
  schedule had no stop at that corner before 2025-11-23. Orleans & Chicago (6662 `6714`), which that note also left
  without a window (88 ft), is the same case before 2025-09-28. The committed windows are unchanged. Overriding them
  is a review for the owner (TODO.md).
- The playbook gotcha "Transit.land answers Unauthorized to feed downloads while its metadata works" described the
  Explorer key; it is rewritten for archive access.

## How to re-check

Run `notebooks/gtfs_history_routes_8_66.ipynb` top to bottom. It downloads only the versions missing from
`data/gtfs/feed_versions/` (one quota hit each) and the two raw day files. Section 3 must show 0 ft against the
`getpatterns` fixtures. Section 8 reprints the 38-row table. A different answer means a refreshed fixture, a changed
validity JSON, or a different version set; the SHA-1 of each zip is its version id. A 401 from `/download` means the
key lost archive access, and a proxy 403 means the blob host left the environment's allowed list.
