# S1a — Archive hunt: findings

Scope: DERISKING.md workstream **S1, step 0 only** — does an existing historical
MBTA dataset already contain prediction-level records carrying the unhappy-path
signals named in `docs/mbta-api.md`? Live capture (the rest of S1) is a separate
session and is not touched here.

All checks below were run against **actual downloaded records**, not documentation,
on 2026-09-06 between roughly 09:20 and 10:00 ET.

---

## Finding 1 — No public archive of MBTA prediction-level records exists. (Answer: NO)

**Question.** Is there an existing archive we can hand to S6 instead of waiting a
week for live capture?

**Answer.** No. Eleven candidate sources were checked. Every historical MBTA
dataset that is public is either (a) *observed events* — what actually happened —
or (b) *pre-aggregated accuracy counts. None of them stores the prediction records
themselves, so none can answer a threshold question of the form "what did the feed
say, and how long before the failure became obvious did it say it?"

**Confidence: high.** The distinction is structural, not a gap in coverage: the
MBTA's public performance pipeline (LAMP) is built to measure realized service, and
it discards the prediction stream after deriving events from it.

### Candidates checked

| # | Candidate | Verified how | Outcome |
|---|---|---|---|
| 1 | LAMP `subway-on-time-performance-v1` | Downloaded `2026-09-03` parquet, 49,622 rows, 27 cols | **Fail** — observed arrival/departure events only. No prediction fields. Rapid transit only. |
| 2 | LAMP `tableau/rail/LAMP_ALL_RT_fields.parquet` | Schema read remotely (duckdb httpfs), 42 cols | **Fail** — same shape, richer joins. No prediction fields. Rapid transit only. |
| 3 | LAMP `gtfs_archive/` (2009→) | Documented + index page | **Fail** — static GTFS schedules only. Useful later for the schedule join, not for predictions. |
| 4 | LAMP `tableau/alerts/LAMP_RT_ALERTS.parquet` | Queried remotely: 4,945,787 rows, 32 cols | **Partial pass — see Finding 2.** Alerts only, but a real historical archive. |
| 5 | MBTA Open Data Portal, "Rapid Transit and Bus Prediction Accuracy Data" | Downloaded the 618 KB CSV: 11,284 rows, 7 cols | **Fail** — weekly aggregates (`weekly, mode, route_id, bin, arrival_departure, num_predictions, num_accurate_predictions`) from 2020-08-07. No record-level data, no commuter rail. |
| 6 | MBTA Open Data Portal, everything else | Enumerated all 203 items under owner `MBTAHUB_ADMIN` via the ArcGIS REST search API | **Fail** — Rapid Transit Events / Travel Times / Headways (2020–2026) are observed events, rapid transit only; "MBTA Commuter Rail Reliability" is aggregate. No prediction-level dataset anywhere in the portal. |
| 7 | MBTA-Performance API (`mbta/transit-performance`) | mbta.com/developers/historical-performance-data | **Fail** — the software does archive predicted arrival/departure events, but the public API was **retired 2024-05-13** and no dump was published. Running it ourselves would be a live capture, not an archive. |
| 8 | `mbta/prediction_analyzer` | Repo README | **Fail** — internal MBTA tool for prediction-accuracy analysis. No public data. |
| 9 | Internet Archive / Wayback | CDX API over `cdn.mbta.com/realtime/*` | **Fail** — `TripUpdates_enhanced.json`: **1 capture** (2023-05-21). `VehiclePositions_enhanced.json`: **1 capture**. `TripUpdates.pb`: **17 captures** spread over 2021–2026. Not a time series; a single snapshot cannot show churn or lead time. |
| 10 | transitfeeds.com / OpenMobilityData, Mobility Database, Transitland | Site fetch (403, Cloudflare challenge), MobilityData FAQ, Transitland feed page | **Fail** — all three archive **GTFS Schedule** versions. GTFS-RT is catalogued as a *URL*, never historized. TransitFeeds is frozen at Feb 2024 and is schedule-only. |
| 11 | `tsdataclinic/gtfs-realtime-capsule`, TransitMatters (`gobble`, dashboard API), HuggingFace/Zenodo/arXiv | Repo pages, API probe, dataset search | **Fail** — capsule is a *tool* to build your own archive; repo archived 2025-08-18, no hosted data. TransitMatters `gobble` reads the V3 stream but emits arrival/departure **events**; its dashboard "predictions" page is accuracy aggregates and `dashboard-api.labs.transitmatters.org` rejects unauthenticated reads (403 `Missing Authentication Token`). No MBTA GTFS-RT prediction archive on HuggingFace, Zenodo, or in the papers found. |

### What this means for the plan

**Live capture stays on the critical path.** S6 cannot be started early against an
archive for the trip-selection, threshold, hysteresis, precedence, confidence, or
lead-time questions. The week is not recoverable.

---

## Finding 2 — One real archive does exist, for alerts. (Answer: YES, partial)

**Question.** Is any part of S6 unblocked today?

**Evidence.** `https://performancedata.mbta.com/lamp/tableau/alerts/LAMP_RT_ALERTS.parquet`

- 4,945,787 rows, 32 columns, no auth, single HTTP file (range-readable — duckdb
  `read_parquet()` over httpfs works without downloading it whole).
- Coverage: **2019-02-01 → live** (max `last_modified_timestamp` was minutes old
  when queried).
- Columns include everything `docs/mbta-api.md` names for alerts and more:
  `cause`, `cause_detail`, `effect`, `effect_detail`, `severity`, `severity_level`,
  `alert_lifecycle`, `duration_certainty`, `header_text`, `description_text`,
  `service_effect_text`, `created_timestamp`, `last_modified_timestamp`,
  `last_push_notification_timestamp`, `closed_timestamp`,
  `active_period.start/end`, and `informed_entity.{route_id, route_type,
  direction_id, stop_id, facility_id, activities}`.
- **Commuter rail is covered.** `CR-Worcester`: 442,885 rows across 30,447 distinct
  alert ids, 2018-09-26 → 2026-09-06.
- `effect_detail` carries the V3-style vocabulary. For `CR-Worcester`:
  `TRACK_CHANGE` 254,507, `DELAY` 151,224, `SERVICE_CHANGE` 28,232, `SHUTTLE` 3,954,
  `CANCELLATION` 1,290, `SUSPENSION` 412, `STATION_CLOSURE` 13, … (top-level `effect`
  is the coarser GTFS-RT enum — `OTHER_EFFECT` dominates, so **filter on
  `effect_detail`, not `effect`**).

**Answer.** The alert-integration portion of `docs/transit-providers.md` — which
alert effects matter, how severity distributes, how long alerts stay open, how
`last_push_notification_timestamp` behaves — can be worked **today**, against eight
years of real commuter-rail history, with no dependency on S1's capture.

**Confidence: high.** Verified by direct query against the live file.

---

## Finding 3 — For commuter rail, two of the four named unhappy-path signals appear to be absent entirely.

This was not the question S1 step 0 asked, but it came out of verifying the fields
and it changes what the capture is for.

**Evidence.** `prototypes/s1a-archive-hunt/probe_v3_fields.py` censuses every live
V3 prediction for a route group. Run twice, ~45 minutes apart:

| Route type | n | `update_type` | `arrival_uncertainty` | `schedule_relationship` | vehicle |
|---|---|---|---|---|---|
| Commuter rail (12 routes) | 111 | **all null** | **all null** | **all null** | 111/111 assigned |
| Heavy rail | 500 | MID_TRIP 233 / REVERSE_TRIP 181 / AT_TERMINAL 86 | 60:233, 120:80, 360:149, null:38 | ADDED 11 | 500/500 |
| Light rail | 500 | MID_TRIP 342 / REVERSE_TRIP 107 / AT_TERMINAL 27 / null 24 | 60:337, 120:23, 360:82, null:58 | SKIPPED 17, CANCELLED 24 | 476/500 |

Both samples agreed to within a few counts. Cross-checked against the raw feed: a
`TripUpdates_enhanced.json` snapshot (1,033 trips) showed `update_type` on 120 of
121 rapid-transit trips, **0 of 17 commuter-rail trips**, and 0 of 895 bus trips;
`uncertainty` on 1,691 rapid-transit stop-time-updates and **0 of 109 commuter-rail
ones**.

**Answer.** On the tracer-bullet route type, `update_type` and `arrival_uncertainty`
look like they simply do not exist. If that holds on a weekday, commuter-rail
unhappy-path detection has to rest on the remaining signals: vehicle assignment
(present), vehicle staleness, `boarding_status`/`status`, the schedule-vs-prediction
join, and alerts.

**Confidence: medium.** Two Sunday-morning samples. Weekday commute windows may
behave differently, and this is exactly what S1's live capture will settle. Do not
rewrite `docs/mbta-api.md` on this alone — but do not assume the fields are there
either.

Related: `status` (from `boarding_status`) *is* populated for commuter rail, but
sparsely and late — a targeted South Station query returned `"All aboard"` on a
departing trip, while both whole-network CR samples had 0/111 non-null. It appears
to fire around terminal boarding, which is close to the moment the rider already
knows. Its lead-time value is an open question for S6.

---

## Finding 4 — Field-provenance corrections for `docs/mbta-api.md`

Established by parsing real feed bytes; these are for the orchestrator to fold in.

1. **`update_type` is not in the standard GTFS-RT protobuf.** Parsed a live
   `TripUpdates.pb` (1,035 entities): the only fields present on `trip_update` are
   `trip`, `stop_time_update`, `vehicle`, `timestamp`. `update_type` exists **only**
   in `TripUpdates_enhanced.json` — and it is not even listed in MBTA's documented
   enhanced-field table, which means it falls under their blanket clause: *"The
   enhanced feeds may include fields other than those listed here. Such fields
   should be treated as experimental, subject to change or removal at any time and
   without advance notice."* Anything we build on `update_type` is building on an
   undocumented field.
2. **`status` likewise** derives from `boarding_status`, an enhanced-JSON-only
   field (this one *is* documented).
3. **`arrival_uncertainty` is not a number of seconds — it is a coded enum**, and
   it *is* in the standard protobuf. Per MBTA's own reference: rail uses
   `60` = trip already started, `120` = terminal/reverse departure, train awaiting
   departure at origin, `360` = terminal/reverse trip, train still completing a
   previous trip. Bus uses `<300` valid, `300` no real-time (schedule-based, no
   vehicle assigned yet), `301` stalled/significantly delayed, `>301` likely invalid.
   `docs/mbta-api.md` currently says ">300s means low-confidence" and
   "`arrival_uncertainty` > 300 seconds". That numerically picks out rail `360` and
   bus `300`+, which is roughly the right set — but the reasoning is wrong, and
   **rail `360` is the interesting one**: it is close to a literal ghost-train
   signal ("a train is scheduled to start this trip but is still finishing another
   one"). Worth treating as a named signal rather than a threshold.
4. **V3 returns `update_type` in UPPERCASE** — `MID_TRIP`, `AT_TERMINAL`, and a
   third value `REVERSE_TRIP` that `docs/mbta-api.md` does not list. The enhanced
   JSON feed uses lowercase (`mid_trip`, `at_terminal`, `reverse_trip`). A string
   comparison written from the current doc would silently never match.
5. **`REVERSE_TRIP` is common** — 181/500 heavy-rail and 90–107/500 light-rail
   predictions. Given that rail `uncertainty` 120 and 360 both describe
   terminal/reverse situations, `REVERSE_TRIP` + `360` together look like the
   strongest available "this train has not started and might not" pair. S6 should
   test that specific conjunction.

**Confidence: high** for 1–4 (parsed from live feed bytes and MBTA's own reference
document), **medium** for the 5 conjunction hypothesis, which is a proposal for S6
to test rather than a result.

---

## What was not done

- **transitfeeds.com was not read directly.** Both `WebFetch` and `curl` got a
  Cloudflare interstitial (403). The conclusion that it is schedule-only rests on
  MobilityData's own statement that it is "a temporary archive for data from 2014 to
  February of 2024" superseded by the Mobility Database, whose historization is
  documented as GTFS Schedule. If someone wants certainty here, opening
  `https://transitfeeds.com/p/mbta` in a browser settles it in ten seconds. It would
  not change the recommendation: even a protobuf archive would lack `update_type`
  and `status` (Finding 4).
- **No non-English / non-US civic mirrors were searched.** Low expected yield for a
  Boston-specific feed.
- **Findings 3 and 4 were not confirmed on a weekday.** Sunday morning only. S1's
  live capture resolves this as a side effect of running.
- **Commuter-rail vehicle staleness was not measured.** It needs a time series,
  which is S1's job.

---

## Recommendation

1. **Do not shortcut S1.** Live capture is the critical path and should keep running.
2. **Start S6's alert work now** against `LAMP_RT_ALERTS.parquet` — it needs nothing
   from S1.
3. **Raise the priority of the secondary rapid-transit capture stop.** If Finding 3
   holds, `update_type` and `arrival_uncertainty` are observable *only* on rapid
   transit, so the secondary stop is not a generalization check any more — it is the
   only place several of the documented signals can be studied at all.
4. **Fold Finding 4 into `docs/mbta-api.md`** (orchestrator's call; this session does
   not edit `docs/`).

---

## Reproducing

```bash
# Finding 3 — live V3 field census by route type (no API key needed)
python3 prototypes/s1a-archive-hunt/probe_v3_fields.py

# Finding 2 — the alert archive
python3 -m pip install duckdb
python3 - <<'PY'
import duckdb
c = duckdb.connect(); c.execute("INSTALL httpfs; LOAD httpfs;")
u = "https://performancedata.mbta.com/lamp/tableau/alerts/LAMP_RT_ALERTS.parquet"
print(c.execute(f"""SELECT effect_detail, count(*) n FROM read_parquet('{u}')
                    WHERE "informed_entity.route_id" = 'CR-Worcester'
                    GROUP BY 1 ORDER BY n DESC""").fetchall())
PY

# Finding 4.1 — update_type is absent from the standard protobuf
python3 -m pip install gtfs-realtime-bindings
curl -s -o /tmp/TripUpdates.pb https://cdn.mbta.com/realtime/TripUpdates.pb
python3 - <<'PY'
from google.transit import gtfs_realtime_pb2 as p
import collections
f = p.FeedMessage(); f.ParseFromString(open('/tmp/TripUpdates.pb','rb').read())
c = collections.Counter()
for e in f.entity:
    for fd, _ in e.trip_update.ListFields(): c[fd.name] += 1
print(len(f.entity), c)   # -> only trip / stop_time_update / vehicle / timestamp
PY

# Finding 1.9 — Wayback capture counts
curl -s "http://web.archive.org/cdx/search/cdx?url=cdn.mbta.com/realtime/TripUpdates_enhanced.json&output=text&fl=timestamp,statuscode"
```

## Infrastructure created

None. This session ran entirely on the laptop, created no Proxmox container, and
downloaded only into the job's scratch directory. Nothing to tear down.
