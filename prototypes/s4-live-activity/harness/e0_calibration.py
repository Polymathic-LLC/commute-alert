#!/usr/bin/env python3
"""E0 — instrument calibration, and the epoch probe that settles F10.

Built ahead of need. Part C shipped to a human with no sender behind it (see the
F9 commit); the fix for that is not to be more careful, it is to build the
instrument before the session that depends on it exists. E0 is the immediate next
step after the instrumented build lands, so it is ready now.

THREE MODES
-----------
`--mode epoch`  (2 sends, ~1 min)  **Run this one first.** Settles F10.
    Two updates, identical but for how `updatedAt` is encoded — one as seconds
    since 1970, one as seconds since 2001. Both are numbers so both decode (F6);
    they differ only in the Date they produce, roughly 31 years apart. The app
    logs the *decoded* value via `contentUpdates`, so the answer comes out of the
    log as a plain ISO timestamp and needs no interpretation:

        the arm whose decoded date is ~now is the epoch ActivityKit reads.

    This is the instrument version of the question the runbook's A2 asks a human
    to answer by squinting at a card. If the two disagree, the instrument wins
    and the disagreement is itself a finding about lock-screen transcription as a
    measurement channel.

`--mode a`      (5 sends, 30 s apart, ~3 min, app FOREGROUNDED)
    Calibrates the widget render log (I1) against in-app `contentUpdates` (I2),
    which is exact while the app lives. Also a first cheap data point on whether
    2/min is accepted at all.

`--mode b`      (4 sends, 15 min apart, 1 h, phone LOCKED and untouched)
    Calibrates I1 in the condition E2 actually runs in, at 4/hour — exactly
    Apple's documented budget, chosen so that throttling is not a plausible
    explanation for a miss. If I1 records 4 of 4 it is trusted at 1.0 and E2's
    drop counts are real drops. If it records fewer, every E2 landing count is a
    lower bound only and the findings will say so.

WHY CALIBRATION COMES BEFORE THE BUDGET RAMP
--------------------------------------------
Every drop count in E2 is `sent − observed`. If I1 silently undercounts, E2
reports a throttle that is really an instrument artifact — the same class of
error as counting 200s, one layer down.

All payloads send `updatedAt` as a NUMBER and pass `refresh_la_fields=False`
(F6/F9). Run `--preflight` before any live session.
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
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "e0-calibration.ndjson"
APPLE_EPOCH_OFFSET = 978_307_200  # 2001-01-01T00:00:00Z in Unix seconds

MODES = {
    #        count, interval_s, description
    "epoch": (2, 20, "epoch probe — settles F10 off the decoded value"),
    "a":     (5, 30, "I1 vs I2, app foregrounded"),
    "b":     (4, 900, "I1 in the locked/unattended condition, 4/hour"),
}


def content_state(mode: str, seq: int, unix: int) -> dict:
    """`headline` carries the correlation key the device echoes back verbatim."""
    if mode == "epoch":
        # seq 1 -> 1970 seconds, seq 2 -> 2001-reference seconds. Same instant,
        # two encodings; whichever decodes to ~now names the epoch.
        use_1970 = seq == 1
        updated_at = unix if use_1970 else unix - APPLE_EPOCH_OFFSET
        label = "1970" if use_1970 else "2001"
        headline = f"S4 E0epoch {seq:02d} {label}"
    else:
        updated_at = unix - APPLE_EPOCH_OFFSET
        headline = f"S4 E0{mode} {seq:02d} n{unix % 10000:04d}"
    return {
        "v": 1,
        "displayStatus": "on_time",
        "headline": headline,
        "minutesToDeparture": seq,
        "updatedAt": updated_at,   # NUMBER, never a string. F6/F9.
    }


def payload_for(mode: str, seq: int, unix: int) -> dict:
    return {"aps": {"event": "update",
                    "content-state": content_state(mode, seq, unix),
                    "timestamp": unix}}


def preflight() -> int:
    from apns_harness import payloads as s2_payloads
    unix = int(time.time())
    ok = True
    print("E0 payloads through S2's check_fatal_shapes + validate:\n")
    for mode in MODES:
        for seq in (1, 2):
            body = payload_for(mode, seq, unix)
            try:
                s2_payloads.check_fatal_shapes(body, s2_payloads.PUSH_TYPES["la-update"])
                s2_payloads.validate(body, s2_payloads.PUSH_TYPES["la-update"])
                print(f"  PASS  mode={mode:<6} seq={seq}  "
                      f"updatedAt={body['aps']['content-state']['updatedAt']}")
            except Exception as exc:
                ok = False
                print(f"  FAIL  mode={mode:<6} seq={seq}  {type(exc).__name__}: {exc}")
    print("\nPREFLIGHT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(MODES))
    ap.add_argument("--token", help="per-activity token; else read from tokens.md")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.preflight:
        return preflight()
    if not args.mode:
        ap.error("--mode is required unless --preflight")

    count, interval, desc = MODES[args.mode]
    token = args.token or s2_tokens.resolve("activity")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"E0  mode={args.mode}: {desc}")
    print(f"E0  {count} sends, {interval}s apart "
          f"(~{count * interval // 60} min), token {token[:6]}…{token[-4:]}")
    if args.mode == "b":
        print("E0  phone must be LOCKED and untouched for the whole hour")
    if args.mode == "a":
        print("E0  app must be FOREGROUNDED for the whole run")
    if args.dry_run:
        for seq in range(1, count + 1):
            print("   ", json.dumps(content_state(args.mode, seq, int(time.time()))))
        return 0

    print()
    with Sender(environment="sandbox") as sender:
        for seq in range(1, count + 1):
            if seq > 1:
                time.sleep(interval)
            unix = int(time.time())
            body = payload_for(args.mode, seq, unix)
            try:
                resp = sender.send(
                    type="la-update", token=token, payload=body,
                    refresh_la_fields=False,
                    extra_log={"experiment": f"E0{args.mode}", "seq": seq},
                )
                row = {"mode": args.mode, "seq": seq,
                       "sent_at": dt.datetime.now(TZ).isoformat(),
                       "headline": body["aps"]["content-state"]["headline"],
                       "updatedAt_sent": body["aps"]["content-state"]["updatedAt"],
                       "status": resp.status_code, "reason": resp.reason,
                       "apns_id": resp.apns_id}
            except Exception as exc:
                row = {"mode": args.mode, "seq": seq,
                       "sent_at": dt.datetime.now(TZ).isoformat(), "error": repr(exc)}
            with OUT.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(f"E0  seq={seq:02d}  {row.get('status')} {row.get('reason') or ''} "
                  f"{row.get('error','')}".rstrip())

    # Said explicitly because this is the exact trap the workstream exists to
    # avoid: the codes above are correlation keys, not results.
    print("\nE0  sends done. These status codes are NOT the measurement.")
    print("E0  The result is in the device log — export it from the app and read:")
    if args.mode == "epoch":
        print("      `content_update` rows: whichever arm's updatedAtDecoded is ~now")
        print("      names the epoch ActivityKit reads a numeric Date against (F10).")
    else:
        print("      `render` rows (I1) vs `content_update` rows (I2), matched on headline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
