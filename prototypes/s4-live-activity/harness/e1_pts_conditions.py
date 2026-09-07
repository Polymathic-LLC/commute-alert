#!/usr/bin/env python3
"""E1 — push-to-start reliability across process, boot and power states.

The question `docs/architecture.md` decision 3 rests on: can the backend start a
Live Activity with no user interaction, whatever state the phone is in?

Clock-driven so neither side waits on the other. The human works the timetable in
RUNBOOK-MORNING.md Part C; this fires on the same clock. Start both at the same
minute and they stay in step without any coordination.

    T+1:30   C2-t1   app force-quit
    T+5:30   C2-t2   app force-quit (second trial)
    T+9:30   C5-t1   Low Power Mode + force-quit
    T+15:00  C3-t1   rebooted, never unlocked (before-first-unlock)
    T+19:30  C4-t1   rebooted, unlocked once, app never launched
    T+23:30  C1-t1   baseline: app used then backgrounded normally

WHY THE BASELINE IS LAST AND NOT FIRST
--------------------------------------
It has to run when the app has recently been foregrounded, which is only true
after the human opens it at the end. Its job is to make a total failure
interpretable: if C2..C4 all produce nothing AND C1 also produces nothing, then
push-to-start is broken on this device or this build and the conditions tell us
nothing. If C1 works and the others don't, the conditions are the finding. Without
it, an all-negative run is uninterpretable, which is the worst outcome available
here — the workstream's headline question answered "maybe".

EVERY PAYLOAD SENDS `updatedAt` AS A NUMBER
-------------------------------------------
F6: ActivityKit's push decoder cannot decode an ISO-8601 string into a Swift
`Date`, and one bad field silently discards the whole push behind a 200. F9: E4's
entire run hit exactly that, because it relied on the harness default which
rewrites the field to ISO-8601. So this script builds its own payload and passes
`refresh_la_fields=False`. Do not remove that without re-reading F9.

Usage:
    python3 e1_pts_conditions.py --start "07:30"        # today, local
    python3 e1_pts_conditions.py --start "07:30" --dry-run
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

TZ = zoneinfo.ZoneInfo("America/New_York")
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "e1-pts-conditions.ndjson"
APPLE_EPOCH_OFFSET = 978_307_200  # 2001-01-01T00:00:00Z, in Unix seconds

# (offset_seconds, routeName, condition description, what the human is doing)
TRIALS = [
    (90,   "S4-E1-C2-t1", "force-quit",                       "app swiped away, phone locked"),
    (330,  "S4-E1-C2-t2", "force-quit (trial 2)",             "app swiped away again"),
    (570,  "S4-E1-C5-t1", "Low Power Mode + force-quit",      "LPM on, app swiped away"),
    (900,  "S4-E1-C3-t1", "rebooted, never unlocked",         "fresh boot, still on passcode screen"),
    (1170, "S4-E1-C4-t1", "rebooted, unlocked, never opened", "unlocked once, app not launched"),
    (1410, "S4-E1-C1-t1", "BASELINE: backgrounded normally",  "app opened then backgrounded"),
]


def payload_for(route: str, unix: int) -> dict:
    return {
        "aps": {
            "event": "start",
            "attributes-type": "CommuteActivityAttributes",
            "attributes": {"routeName": route, "stopName": "Boston Landing"},
            "content-state": {
                "v": 1,
                "displayStatus": "on_time",
                "headline": f"S4 E1 {route}",
                "minutesToDeparture": 7,
                # NUMBER, not a string. See F6/F9.
                "updatedAt": unix - APPLE_EPOCH_OFFSET,
            },
            "alert": {"title": route, "body": "push-to-start condition trial"},
            "timestamp": unix,
        }
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help='"HH:MM" today, local time')
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(TZ)
    hh, mm = (int(x) for x in args.start.split(":"))
    t0 = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t0 < now - dt.timedelta(minutes=2):
        t0 += dt.timedelta(days=1)

    token = s2_tokens.resolve("pts")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"E1  T+0 = {t0:%Y-%m-%d %H:%M:%S %Z}")
    print(f"E1  push-to-start token {token[:6]}…{token[-4:]}\n")
    for off, route, cond, doing in TRIALS:
        due = t0 + dt.timedelta(seconds=off)
        print(f"  T+{off//60:>2}:{off%60:02d}  {due:%H:%M:%S}  {route:<14} {cond}")
    if args.dry_run:
        print("\n(dry run — nothing sent)")
        return 0

    print()
    with Sender(environment="sandbox") as sender:
        for off, route, cond, doing in TRIALS:
            due = t0 + dt.timedelta(seconds=off)
            delay = (due - dt.datetime.now(TZ)).total_seconds()
            if delay < -60:
                print(f"E1  SKIP {route} (already past)")
                continue
            if delay > 0:
                time.sleep(delay)

            unix = int(time.time())
            try:
                resp = sender.send(
                    type="la-start",
                    token=token,
                    payload=payload_for(route, unix),
                    refresh_la_fields=False,   # F9 — do not let the default
                                               # rewrite updatedAt to ISO-8601
                    extra_log={"experiment": "E1", "route": route, "condition": cond},
                )
                row = {
                    "route": route, "condition": cond, "human_doing": doing,
                    "sent_at": dt.datetime.now(TZ).isoformat(),
                    "offset_s": off,
                    "status": resp.status_code, "reason": resp.reason,
                    "apns_id": resp.apns_id, "apns_unique_id": resp.apns_unique_id,
                }
            except Exception as exc:
                row = {"route": route, "condition": cond,
                       "sent_at": dt.datetime.now(TZ).isoformat(),
                       "offset_s": off, "error": repr(exc)}

            with OUT.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            # The status is logged for correlation only. It says nothing about
            # whether a card appeared — that is the human's column, and F6
            # showed a 200 alongside a silent no-op three times over.
            print(f"E1  {route:<14} {row.get('status')} {row.get('reason') or ''} "
                  f"{row.get('error','')}".rstrip())

    print("\nE1  all trials sent. The result is the human's card-name column, not these codes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
