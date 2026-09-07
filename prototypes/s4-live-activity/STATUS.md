STATUS: RUNNING
Last updated: 2026-09-07 02:05 EDT
Summary: E4 finished early and clean. A Live Activity's push TOKEN dies at exactly 8 hours (whether the card dies with it is a separate question, still open), and APNs DOES report a dead activity (`410 ExpiredToken`, timestamped to the second) — the half of the question that was genuinely in doubt, answered the good way. Push-to-start also resolved earlier: it works, and had been failing on one mis-encoded field. Five findings now closed. No measurement is running; nothing is consuming the device.

## Device state — for S5, and for the rebuild hold

**THE REBUILD HOLD CAN BE LIFTED NOW.** E4 completed at 00:50 EDT, four hours earlier than the
04:45 horizon, because the token died at 8 h and the run stopped on confirmation. Nothing S4
is doing depends on the current build any more. A rebuild is safe from this moment.

**S4 still needs the device** for E0, E1, E2, E3, E5 and E6 — the instrumented build, the
push-to-start reliability session, and the budget ramp. I will say here explicitly when I am
finished with the phone. S5 should not start yet.

Left on the device: the `S4-B2` and `S4-B3` cards from 17:11:53–55, which expire on their own
at ~01:12 if card lifetime tracks token lifetime and 8 h is uniform — both untested. The
locally-started activity's token died at 00:44:01.
Nothing needs cleaning up by hand; no permissions were changed.

## Needs from human

Morning batch, unchanged from what the orchestrator is already relaying, with one addition
that is now more valuable than it was:

1. **Which cards are still on the Lock Screen** — the no-push one, `S4-B2-…`, `S4-B3-…`? For
   any that are gone, roughly when were they last seen?
2. **Was the no-push card gone by around 00:45?** Its token died at exactly 00:44:01. Whether
   the *card* vanished at the same moment is a separate question this run cannot answer, and
   it decides whether a user ever sees a stale card the backend can no longer reach.
3. **The loading indicator** — has that card *ever* shown real text ("Local start — no push
   involved"), or has it looked like that since it started?
4. Is an Apple Watch paired? yes/no.
5. iPhone Mirroring — can they screenshot the Lock Screen from the Mac?

## Results

| Experiment | Status | Result |
|---|---|---|
| E4 — 8-hour cap | **done** | *token* dies at 8 h exactly; `410 ExpiredToken` at 00:44:01. Card lifetime NOT measured (F5) |
| E8 — restart reconciliation | **done** (free) | works; token-only pushing survived 8 h (F5) |
| E1b — push-to-start payload | **done** | numeric `Date` required, ISO-8601 fatal (F6) |
| E5 — concurrency | partial (free) | ≥3 coexist, separately presented (F8) |
| E0, E1, E2, E3, E6, E7, E9 | not started | need the instrumented build and/or a human session |

Data: `data/e4-heartbeats.ndjson` (27 rows), `data/e1b-date-encoding.ndjson`, `logs/e4.log`.
All gitignored.

## Next — blocked only on the human, nothing left for S4 to build

**`RUNBOOK-MORNING.md` is written and ready to relay.** One sitting: Part A is 2 minutes and
must happen *before* the phone is unlocked or rebuilt; Part B is the ~10-minute install;
Part C is a clock-driven push-to-start session (force-quit / Low Power Mode /
before-first-unlock / never-launched-this-boot) with a five-row log format.

The instrumented build is **done and verified** — `probe-app/` compiles clean on the simulator
and unsigned device slices with zero warnings, and passes S3's `plutil` installability gate on
both the `.app` and the `.appex`. That gate is what caught yesterday's `CoreDeviceError 3000`,
so it was run rather than trusting BUILD SUCCEEDED. Note for the relay: it is a **different
`.xcodeproj` path** from yesterday's (`probe-app/S3Probe.xcodeproj`), same bundle ID and team,
so signing needs no new setup.

After the runbook: E0 calibration, E2 budget ramp, E3 collapse-id, E6 ending, E10 staleness,
then E7 (Watch) once paired.

## Activity log

- Read DERISKING.md S4, S2's FINDINGS, S3's sources and tokens.
- Lifted S2's live-send hold; wrote PROTOCOL.md (nine experiments, each with claim, sample
  size, device-side observer and falsifier, plus an explicit "Not measured" section).
- Re-scoped per the orchestrator when the human offered to be the sensor: cut the HTTP
  collector, ATS local networking and upload panel; kept only what has no human substitute.
- Ran E4 as a detached process. 27 heartbeats, sharp transition at 8 h, confirmed on repeat.
- Ran E1b: three push-to-start arms differing only in `updatedAt` encoding. Resolved F6.
- Corrected F1 and F2 in place when human observations falsified them; corrected the
  orchestrator twice on facts it had reported as established.
- Copied the probe app into this prototype's own directory rather than editing S3's worktree.
- Built E0 (calibration + the epoch probe that settles F10 by instrument) and E1's Part C
  runner, both preflighted against S2's live guards. E0 exists *before* the session that needs
  it — the Part C failure was not "review runbooks harder", it was that an instrument must
  exist before the session consuming it.
- Swept my own files for two drift classes after the orchestrator found them in its record,
  and **found both in mine**: a corrected heartbeat count left stale in one place, and the
  token-lifetime/activity-lifetime conflation left standing in this file's Summary line — the
  most-read line in the file the orchestrator polls, corrected carefully in FINDINGS and not
  here. Both fixed. The lesson is the one predicted: an early confident summary drifts once
  the evidence sharpens, and the summary is the last place anyone looks.

## Open question held here rather than sent (orchestrator asked for quiet)

If A1/A3 show the card outlived its token, the design consequence is larger than the cap
itself: a backend would be unable to reach or correct a card the user can still see, and no
APNs response would reveal it. Worth deciding, before E2, whether that warrants a dedicated
experiment rather than a sub-question of E4.
