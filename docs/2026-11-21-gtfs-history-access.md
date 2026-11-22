# CTA GTFS for routes 8, 65 and 66: ids join one to one with Bus Tracker; past versions are listed but not yet downloadable (measured 2026-11-21)

Tags: `kind:measurement source:gtfs source:bustracker topic:identifiers topic:network`

Contains data from [Transitland](https://www.transit.land/terms): the CTA feed version list below comes from its API.
Its attribution terms, quoted in full, are in ADR-013.

Historical GTFS stop lists could settle the stop-validity cases that the ping-distance method cannot see: Wells & Chicago
and the two Blue Line stops at Halsted, Grand and Milwaukee, which sit at corners of the old routes
(`docs/2026-11-21-stop-validity-windows.md`). They could also measure how promptly CTA's schedule follows a detour. This
note is the first look, for the TODO item "Historical pattern geometry from GTFS": what is reachable, and whether GTFS ids
join to Bus Tracker's. It changes no view, threshold or window. The history itself is blocked on Transit.land access,
requested by the owner on 2026-11-21.

## Measurement

The owner allowed `www.transitchicago.com`, `transit.land` and `web.archive.org` for the cloud environment on 2026-11-21.
The Transit.land key (the owner's Explorer access) is a network secret on that environment: the session proxy adds it to
requests to `transit.land`, and no environment variable or `.env` entry holds it.

| Source | What answered | Contents reachable here |
|---|---|---|
| CTA, `https://www.transitchicago.com/downloads/sch_data/google_transit.zip` | 51,360,701 bytes, `Last-Modified` 2026-11-10 18:22 UTC; `calendar.txt` 2026-10-29 to 2026-12-31 | the current version only |
| Transit.land feed `f-dp3-cta` | 184 versions fetched 2016-02-13 to 2026-11-11, 31 of them since 2024-06, with dates and file lists | none: `feed_versions/<sha1>/download` and `feeds/f-dp3-cta/download_latest_feed_version` answer 401 `{"error":"Unauthorized"}` to an Explorer key; only the latest version is imported into the queryable API (routes and stops of older versions come back empty) |
| Wayback Machine | curl error 35, the connection reset during the TLS handshake, for the CDX index and the front page alike, with the host allowed | none from the cloud environment |

The current CTA feed against the cached `getpatterns` stop lists (`cta.bustracker.pattern_stops_table`), stops per
pattern:

| Pattern | getpatterns | Same stops in GTFS | Differences |
|---|---|---|---|
| 6662 (66 east) | 69 | 69 | none |
| 6665 (66 west) | 70 | 70 | none |
| 6656, 6657 (65) | 76, 76 | 76, 76 | none |
| 9368 (8 south) | 107 | 106 | GTFS lacks `18871` (Halsted & 56th Street) |
| 9376 (8 north) | 104 | 102 | GTFS lacks `18872` (Halsted & 56th Street) and `5888` (Halsted & 57th Street) |

The Transit.land versions around the dated geometry changes of routes 8 and 66, with the full hashes the downloads will
need:

| Fetched | Service dates | sha1 |
|---|---|---|
| 2025-06-10 | 2025-06-09 to 2025-08-31 | `b01dc2d99d3c23362ccf7fc8f95263ca63ce2084` |
| 2025-07-11 | 2025-07-08 to 2025-09-30 | `78428dc43416f3a0be254cfcb2ea05ed2f65ebc9` |
| 2025-08-14 | 2025-08-12 to 2025-10-31 | `e3ebf32877de205c8bf930c77bfb366c19901d48` |
| 2025-09-09 | 2025-09-03 to 2025-11-30 | `ccdead314c38d04fde56933b09e6246e180037d4` |
| 2025-09-25 | 2025-09-24 to 2025-11-30 | `a664d63ce34554f88476278df6a5b66c873db9ee` |
| 2025-10-13 | 2025-09-24 to 2025-11-30 | `b99c500d69fc2661292a6dc3b23511e86765ff3b` |
| 2025-10-27 | 2025-10-20 to 2025-12-31 | `c07e68317b3e4452accfc9f09805727a88937458` |
| 2025-11-20 | 2025-11-19 to 2026-01-31 | `14d83314a4f56f375d6336a4bb7528df4487b055` |
| 2025-12-19 | 2025-12-16 to 2026-02-28 | `8e03d71e0152ea0c012488f6637b362d783a0412` |
| 2026-01-08 | 2026-01-06 to 2026-03-31 | `8e20b5d4fe7fe6f6a8da08a761f250947e4fccb9` |

## Facts confirmed

- **GTFS `stop_id` is the Bus Tracker `stpid`.** The five stops checked (`18803`, `15368`, `15374`, `15341`, `18786`) have
  the same names in both, and positions within about 40 ft. The dominant patterns' stop lists agree id for id, apart from
  three route 8 stops.
- **GTFS `shape_id` minus 68,200,000 is the Bus Tracker `pid`** on routes 8, 65 and 66: the 25 shapes of their trips give
  the 24 `getpatterns_ok` pids of `notebooks/routes_8_65_66_pids.json` and 29292 (route 65, 6 trips). ADR-009 described
  the shape id's suffix as the pattern id; the arithmetic form also covers five-digit pids (`68210949` is 10949). Shape ids
  elsewhere in the feed run to 309,300,138, so the offset is not claimed for other routes or modes.
- **The current schedule carries the 2025 detours**: for 6662, 6665, 6656 and 6657 its stop lists equal today's
  `getpatterns` lists.
- **Explorer access reads Transit.land metadata, not its archive.** The owner reports that Hobbyist/Academic access allows
  500 historical feed downloads a month and requires acknowledging Transit.land in published work; requested 2026-11-21,
  under review.
- **The version dates line up with the measured changes, which is suggestive only.** CTA published versions valid from
  2025-08-12, 2025-09-24 and 2025-11-19, three to six days before each geometry change measured from raw pings (2025-08-17;
  2025-09-27 and -28; 2025-11-23 to 25). Whether those versions carry the detours is unverified until they can be
  downloaded.

## How to re-check

- Current feed: `curl -sS -I -L https://www.transitchicago.com/downloads/sch_data/google_transit.zip`, then read
  `trips.txt` and `stop_times.txt` from the zip for routes 8, 65 and 66, map `shape_id - 68200000` to the pid, and compare
  each pid's stop set with `cta.bustracker.pattern_stops_table`.
- Version list: `https://transit.land/api/v2/rest/feeds/f-dp3-cta/feed_versions?limit=100`, paging with `after`.
- Downloads, once access is granted: `https://transit.land/api/v2/rest/feed_versions/<sha1>/download` for the hashes above.
  A 401 means the key still lacks archive access; check the plan before the request.
