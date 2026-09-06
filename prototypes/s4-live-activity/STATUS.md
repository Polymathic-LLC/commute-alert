STATUS: RUNNING
Last updated: 2026-09-06 17:15 EDT
Summary: The corrected push-to-start still started nothing — that is now the workstream's headline open thread, and a three-arm test that resolves it is already sent and waiting on one glance. E4 (8-hour cap) runs detached until 04:45 EDT and needs nothing from this session. Going quiet on the orchestrator's instruction: no further building or reporting tonight.

## Device state — for S5

**S4 is USING the device; a 12-hour measurement is running against it overnight.**
Do not start S5 device work. I will say so here explicitly when I am done with the phone,
even if I am still analyzing.

Left on the device: one locally-started activity (under measurement by E4), plus up to three
push-started cards if any E1b arm succeeds. **S4 cannot end a push-started activity** — that
needs a per-activity token only the app can see, and the installed build does not capture one
(finding F4). Any E1b card that appears will self-expire, or the human can long-press and
dismiss it. Nothing is broken; it is a known limit of the current build, and the instrumented
build fixes it.

## Needs from human

One glance, whenever convenient — tonight or first thing tomorrow. It resolves the biggest
open question in the workstream.

1. **Lock Screen, without unlocking: how many Live Activity cards, and what is the small grey
   top line of each?** The possible top lines are `CR-Worcester`, `S4-B1-iso`,
   `S4-B2-epoch`, `S4-B3-ref2001`. Reading me the list of names *is* the experiment.
2. **Did any notification banners appear around 17:12 EDT, and what did they say?** Each arm
   carried a banner titled with its own name. A banner without a card separates "the push was
   never processed" from "it was processed and the content was rejected".
3. **The loading symbol.** On the card that is already there: has it *ever* shown real text —
   specifically "Local start — no push involved" — or has it looked like that since it
   started?
4. **Overnight: leave the phone alone.** No rebuild, no force-quit, no reboot, don't open
   S3 Probe. A rebuild in particular would terminate the running activity and truncate E4.
5. **Morning, 1 min:** same look. If a card is gone, roughly when was it last seen?
6. **Whenever:** is an Apple Watch paired? yes/no + watchOS version. Decides whether E7 is
   measurable or is written up as "unmeasured, because —".
7. **New, cheap:** they mentioned seeing the activity "on my laptop" — presumably iPhone
   Mirroring. If so, can they screenshot the Lock Screen from the Mac? That would be a second
   observation channel at zero extra cost to them.

## Running now

| What | Started | Ends | Human needed |
|---|---|---|---|
| E4 — 8-hour cap, 49 heartbeats, detached process | 17:33 EDT | 04:45 EDT | one look in the morning |
| E1b — 3 push-to-start arms, sent 17:11 EDT | done | — | ask 1 above |

Logs: `logs/e4.log`, `data/e4-heartbeats.ndjson`, `data/e1b-date-encoding.ndjson` (gitignored).

## Built, not yet installed

`probe-app/` — a copy of S3's probe with S4 instrumentation added (`S4Log.swift`, render
logging from the widget process, `Activity.activityUpdates` token capture still to wire).
Deliberately **not** installed tonight: installing it would terminate the activity E4 is
measuring. It is tomorrow's work.

## Activity log

- Read DERISKING.md S4, S2's FINDINGS, S3's sources and tokens.
- Lifted S2's live-send hold. S4-A1 (corrected push-to-start) and S4-A2 (update to the
  hours-old per-activity token) both returned 200 at 16:57.
- Wrote PROTOCOL.md — nine experiments, each with claim / protocol / sample size /
  device-side observer / falsifier, plus an explicit "Not measured" section.
- Re-scoped per the orchestrator: dropped the HTTP collector, ATS local networking and the
  upload panel. Kept only what no human can observe — the widget-process render log,
  `Activity.activityUpdates` token capture, and Files-app export.
- Launched E4 as a detached process; verified it survives independently of this session.
- **Human observation at ~17:06: one card only, the locally-started one, showing a loading
  indicator.** So the corrected push-to-start rendered nothing — the snake_case fix was
  necessary but not sufficient. Recorded as F6.
- Designed and sent E1b: three push-to-start arms differing only in how `ContentState.updatedAt`
  is encoded (ISO-8601 string / Unix epoch / seconds-since-2001). One glance names the winner,
  or proves the cause is structural. All three returned 200, which as ever means nothing.
- Copied the probe app into this prototype's own directory rather than editing S3's worktree
  — cross-worktree writes are blocked, and the plan says each session owns one directory.
