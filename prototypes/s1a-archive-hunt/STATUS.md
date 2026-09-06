STATUS: DONE

Last updated: 2026-09-06 ~10:00 ET

**Summary: NO usable prediction-level archive exists. Live capture stays on the
critical path — S6 cannot be started early on the threshold questions.** One real
archive was found, for **alerts only**, and it unblocks S6's alert work today.

## Headline results

1. **Negative on the main question.** Eleven candidate sources checked against real
   downloaded records. Every public historical MBTA dataset is either *observed
   events* (what happened) or *pre-aggregated accuracy counts*. None stores the
   prediction records themselves, so none can answer a lead-time or threshold
   question. Confidence: high — this is structural, not a coverage gap.
2. **Positive, partial.** `https://performancedata.mbta.com/lamp/tableau/alerts/LAMP_RT_ALERTS.parquet`
   — 4.9M rows, 32 columns, no auth, 2019-02-01 → live. `CR-Worcester` alone has
   442,885 rows / 30,447 distinct alerts back to 2018-09-26, with the V3-style
   vocabulary in `effect_detail` (TRACK_CHANGE 254k, DELAY 151k, SHUTTLE 4k,
   CANCELLATION 1.3k, SUSPENSION 412). **S6's alert-integration work can start now.**
3. **Unexpected, and it matters more than the archive answer.** On commuter rail —
   the tracer-bullet route type — `update_type`, `arrival_uncertainty`, and
   `schedule_relationship` were **null in 111/111 live predictions, twice, 45 minutes
   apart**. Rapid transit is rich in all three. Two of the four unhappy-path signals
   named in `docs/mbta-api.md` may not exist at all for `CR-Worcester`. Confidence:
   medium (Sunday samples only) — S1's weekday capture settles it.
4. **Four field-provenance corrections for `docs/mbta-api.md`**, established from
   live feed bytes: `update_type` is enhanced-JSON-only *and undocumented/experimental*;
   `status` is enhanced-JSON-only; `arrival_uncertainty` is a coded enum (rail
   60/120/360), not seconds; and V3 returns `update_type` UPPERCASE with a third
   value `REVERSE_TRIP` the doc omits — a comparison written from the current doc
   would never match. Details in FINDINGS.md, Finding 4.

## Needs from human

**Nothing blocking. One decision to fold, and one optional 10-second check.**

1. **Decision — reprioritise S1's secondary rapid-transit capture stop.**
   S1's brief treats the secondary rapid-transit stop as a "does this generalize?"
   check. If result 3 above holds on a weekday, it is not that any more: rapid
   transit is the *only* place `update_type` and `arrival_uncertainty` are observable
   at all, so it becomes the primary source for those two signals while
   `CR-Worcester` carries the schedule-join, vehicle-staleness, and alert signals.
   Someone should decide whether S1 raises the rapid-transit stop to equal capture
   fidelity (same SSE stream + `/vehicles` + `/schedules` cadence, not a thinner
   sample). This does not block S1 from running as briefed today.

2. **Optional — open `https://transitfeeds.com/p/mbta` in a browser and say whether
   it lists any *realtime* archive with downloadable past snapshots.**
   Both automated fetches hit a Cloudflare challenge (403). Everything else says
   TransitFeeds is GTFS-schedule-only and frozen at Feb 2024, so this is a
   completeness check, not a live lead — and even a protobuf archive would lack
   `update_type` and `status`, so it would not change the recommendation.

## Recommendation to the orchestrator

- Keep S1's live capture running; do not gate anything on an archive.
- Start S6's alert-integration work now against `LAMP_RT_ALERTS.parquet`.
- Fold Finding 4 into `docs/mbta-api.md`; hold Finding 3 until weekday capture
  confirms it.

## Activity log

- Read DERISKING.md S1 step 0 and `docs/mbta-api.md`; fixed the single criterion.
- Surveyed 11 candidate sources breadth-first: MBTA LAMP (4 datasets), MBTA/MassDOT
  Open Data Portal (all 203 items enumerated via ArcGIS REST), MBTA-Performance API,
  `mbta/prediction_analyzer`, Internet Archive CDX, transitfeeds/OpenMobilityData,
  Mobility Database, Transitland, `tsdataclinic/gtfs-realtime-capsule`,
  TransitMatters (`gobble` + dashboard API), HuggingFace/Zenodo/arXiv.
- Verified the two best candidates deeply against downloaded records: LAMP
  subway-on-time-performance parquet (49,622 rows / 27 cols) and the Open Data
  Portal prediction-accuracy CSV (11,284 rows / 7 cols). Both fail the criterion.
- Parsed a live `TripUpdates.pb` and `TripUpdates_enhanced.json` to establish which
  fields live where; ran a live V3 field census twice (`probe_v3_fields.py`).
- Wrote FINDINGS.md. No Proxmox container created; nothing to tear down. No captured
  data committed (scratch downloads went to the job tmp dir, outside the repo).
