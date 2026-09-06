#!/usr/bin/env python3
"""E4 — the 8-hour cap. Long unattended heartbeat run.

Sends `la-update` heartbeats to a per-activity Live Activity token and records
what APNs says, until the token is definitively dead or 12 h have elapsed.

This run produces TWO findings, and the second one may matter more
------------------------------------------------------------------
(1) *When does the activity end?*  If APNs ever starts answering `410
    Unregistered` / `403 ExpiredToken`, the system-imposed end is bracketed by

        (last heartbeat that returned 200, first heartbeat that returned 410)

    as tightly as the heartbeat spacing — 5 min across the window where the cap
    is expected.

(2) *Can the sender find out at all?*  This is the part that is genuinely in
    doubt, and it is deliberately not assumed. Today APNs returned 200 for a
    payload the device could not decode, and 200 again for a per-activity token
    two hours old. There may be **no response code that ever tells a backend an
    activity is unhealthy or gone.** If all 49 heartbeats return 200 and the
    human reports in the morning that the card vanished hours ago, then finding
    (1) is unmeasurable from the server and finding (2) is:

        the server can never know whether its updates are landing,
        and the product must be designed to tolerate that.

    That is a first-order result for backend design, not a failed experiment. So
    this script never treats 200 as success — it only records, and it runs the
    full 12 h horizon unless a token death is observed and confirmed.

What this run cannot establish on its own: whether the *card* left the Lock
Screen at the moment the token died. That needs one human look in the morning,
and it is the sub-question that matters more than the cap itself — a backend
happily collecting 200s for an activity nobody can see is precisely the failure
mode the product must not have.

Usage:
    python3 e4_cap.py --start "2026-09-06 16:37:00" [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import zoneinfo

S2 = pathlib.Path(
    "/Users/bradleybares/Git/commute-alert/.claude/worktrees"
    "/s2-apns-harness/prototypes/s2-apns-harness"
)
sys.path.insert(0, str(S2))

from apns_harness import tokens as s2_tokens  # noqa: E402
from apns_harness.api import Sender  # noqa: E402
from apns_harness.payloads import example_payload  # noqa: E402

TZ = zoneinfo.ZoneInfo("America/New_York")
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "e4-heartbeats.ndjson"

# APNs reasons that mean "this activity is gone" — the thing we are bracketing.
DEAD_REASONS = {"Unregistered", "ExpiredToken", "BadDeviceToken", "DeviceTokenNotForTopic"}

# Elapsed-time schedule, in minutes since the activity started.
#   - every 30 min normally
#   - every 5 min across 7 h 00 m .. 9 h 30 m, where the 8 h cap is expected.
#     The window is deliberately wider than the cap it is hunting: this
#     activity's start time is only known to ±10 min (the human started it by
#     hand during the S3 runbook and nobody recorded the minute). The wall-clock
#     bracket on a token death is still exact; only its mapping onto "elapsed
#     since start" carries that ±10 min.
#   - carry on to 12 h, because "no cap on this OS" is also a finding
TIGHT_FROM, TIGHT_TO, TIGHT_STEP = 420, 570, 5
COARSE_STEP, HORIZON = 30, 720


def schedule() -> list[int]:
    marks = set(range(COARSE_STEP, HORIZON + 1, COARSE_STEP))
    marks |= set(range(TIGHT_FROM, TIGHT_TO + 1, TIGHT_STEP))
    return sorted(m for m in marks if m <= HORIZON)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True,
                    help='activity start, local time, "YYYY-MM-DD HH:MM:SS"')
    ap.add_argument("--start-uncertainty-min", type=int, default=3,
                    help="how well the start time is known; recorded, not used")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    t0 = dt.datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
    token = s2_tokens.resolve("activity")
    marks = schedule()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"E4  activity start {t0.isoformat()}  (±{args.start_uncertainty_min} min)")
    print(f"E4  token {token[:6]}…{token[-4:]}  ({len(token)} hex)")
    print(f"E4  {len(marks)} heartbeats, horizon {HORIZON} min")
    if args.dry_run:
        now = dt.datetime.now(TZ)
        for m in marks:
            due = t0 + dt.timedelta(minutes=m)
            print(f"     +{m:>4} min  {due:%H:%M:%S}  {'PAST' if due < now else ''}")
        return 0

    dead_streak = 0
    with Sender(environment="sandbox") as sender:
        for n, m in enumerate(marks, 1):
            due = t0 + dt.timedelta(minutes=m)
            delay = (due - dt.datetime.now(TZ)).total_seconds()
            if delay < -90:
                print(f"E4  skip +{m} min (already past)")
                continue
            if delay > 0:
                time.sleep(delay)

            elapsed = dt.datetime.now(TZ) - t0
            hh, mm = divmod(int(elapsed.total_seconds()) // 60, 60)
            headline = f"S4-E4 hb={n:03d} elapsed={hh}h{mm:02d}m"

            try:
                resp = sender.send(
                    type="la-update",
                    token=token,
                    payload=example_payload("la-update"),
                    headline=headline,
                    extra_log={"experiment": "E4", "heartbeat": n, "elapsed_min": m},
                )
                row = {
                    "hb": n, "target_elapsed_min": m,
                    "sent_at": dt.datetime.now(TZ).isoformat(),
                    "elapsed": f"{hh}h{mm:02d}m", "headline": headline,
                    "status": resp.status_code, "reason": resp.reason,
                    "apns_id": resp.apns_id, "apns_unique_id": resp.apns_unique_id,
                    "apns_timestamp": resp.timestamp,
                }
            except Exception as exc:  # network blip must not end a 12 h run
                row = {"hb": n, "target_elapsed_min": m,
                       "sent_at": dt.datetime.now(TZ).isoformat(),
                       "elapsed": f"{hh}h{mm:02d}m", "error": repr(exc)}

            with OUT.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(f"E4  +{m:>4}min  {row.get('status')} {row.get('reason') or ''} "
                  f"{row.get('error','')}".rstrip())

            if row.get("reason") in DEAD_REASONS:
                dead_streak += 1
                # Confirm it is persistent, not a one-off, before calling it.
                if dead_streak >= 2:
                    print(f"E4  token dead and confirmed at +{m} min — stopping")
                    break
            elif row.get("status") == 200:
                dead_streak = 0

    print("E4  run complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
