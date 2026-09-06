#!/usr/bin/env python3
"""E1b — why did the corrected push-to-start still start nothing?

At 16:57:09 a push-to-start with keys matching S3's Swift structs exactly
returned 200 and produced no card. The snake_case fix was necessary but not
sufficient. Something else in the payload is still being rejected by
ActivityKit's decoder, and a decode failure is silent by construction: iOS
creates nothing and tells nobody.

LEADING HYPOTHESIS: `ContentState.updatedAt` is a Swift `Date`, and we are
encoding it wrongly.

S2 flagged this as its one unresolved payload question and shipped ISO-8601 on
Apple DTS guidance, at medium confidence. But `JSONDecoder`'s *default*
`dateDecodingStrategy` is `.deferredToDate` — a bare number of seconds since
2001-01-01. If ActivityKit's push decoder is a stock `JSONDecoder` with nothing
customised, then an ISO-8601 *string* fails to decode a `Date`, the whole
`ContentState` fails with it, and the activity is never created. One wrong field
kills the entire push, which is exactly the symptom.

That single cause would explain both open failures at once: the push-to-start
that started nothing, and the `la-update` that may never have applied.

THE TEST. Three push-to-start sends, identical but for the encoding of
`updatedAt`, each with a distinct `attributes.routeName` — which is rendered on
the card's top line, so one glance at the Lock Screen names the winner:

    S4-B1-iso      "2026-09-06T21:50:00Z"   ISO-8601 string   (repeat of what failed; n was 1)
    S4-B2-epoch    1788730200               Unix epoch seconds
    S4-B3-ref2001  810422200                seconds since 2001-01-01  <-- JSONDecoder default

Each also carries a distinct alert title. If a banner appears for an arm whose
card does not, the push was delivered and processed and the failure is
specifically in decoding `ContentState` — which separates "APNs/ActivityKit
never saw it" from "it was decoded and rejected".

WHAT WOULD FALSIFY THE HYPOTHESIS: all three arms produce no card. Then the
encoding of `updatedAt` is not the cause, push-to-start is failing structurally
on this device, and that is a far more serious finding for the product — it is
the mechanism `docs/architecture.md` decision 3 depends on.

Cost: three pushes and one human glance.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import sys
import zoneinfo

S2 = pathlib.Path(
    "/Users/bradleybares/Git/commute-alert/.claude/worktrees"
    "/s2-apns-harness/prototypes/s2-apns-harness"
)
sys.path.insert(0, str(S2))

from apns_harness import tokens as s2_tokens  # noqa: E402
from apns_harness.api import Sender  # noqa: E402

TZ = zoneinfo.ZoneInfo("America/New_York")
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "e1b-date-encoding.ndjson"

# 2001-01-01T00:00:00Z in Unix seconds — the offset JSONDecoder's default
# .deferredToDate strategy works in.
APPLE_EPOCH_OFFSET = 978_307_200


def arms(now: dt.datetime) -> list[tuple[str, object, str]]:
    unix = int(now.timestamp())
    return [
        ("S4-B1-iso",
         now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "ISO-8601 string (what failed at 16:57; n was 1)"),
        ("S4-B2-epoch",
         unix,
         "Unix epoch seconds, numeric"),
        ("S4-B3-ref2001",
         unix - APPLE_EPOCH_OFFSET,
         "seconds since 2001-01-01, numeric — JSONDecoder default"),
    ]


def payload_for(route: str, updated_at: object, unix: int) -> dict:
    return {
        "aps": {
            "event": "start",
            "attributes-type": "CommuteActivityAttributes",
            "attributes": {"routeName": route, "stopName": "Boston Landing"},
            "content-state": {
                "v": 1,
                "displayStatus": "on_time",
                "headline": f"S4 E1b {route}",
                "minutesToDeparture": 9,
                "updatedAt": updated_at,
            },
            "alert": {"title": route, "body": f"push-to-start arm {route}"},
            "timestamp": unix,
        }
    }


def main(sender: "Sender | None" = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(TZ)
    unix = int(now.timestamp())
    token = s2_tokens.resolve("pts")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    print(f"E1b  push-to-start token {token[:6]}…{token[-4:]} ({len(token)} hex)")
    for route, value, why in arms(now):
        body = payload_for(route, value, unix)
        print(f"\n  {route:<14} updatedAt={value!r}   {why}")
        if args.dry_run:
            print("    " + json.dumps(body["aps"]["content-state"]))
            continue

        # refresh_la_fields=False is essential: the harness helpfully rewrites a
        # string `updatedAt` to a fresh ISO-8601 stamp, which would silently
        # convert all three arms into the arm that already failed. aps.timestamp
        # is set by hand above to keep Apple's update ordering intact.
        assert sender is not None
        resp = sender.send(
            type="la-start",
            token=token,
            payload=copy.deepcopy(body),
            refresh_la_fields=False,
            extra_log={"experiment": "E1b", "arm": route},
        )
        row = {
            "arm": route, "updatedAt": value, "why": why,
            "sent_at": dt.datetime.now(TZ).isoformat(),
            "status": resp.status_code, "reason": resp.reason,
            "apns_id": resp.apns_id, "apns_unique_id": resp.apns_unique_id,
        }
        with OUT.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"    -> {resp.status_code} {resp.reason or ''} apns-id={resp.apns_id}")

    return 0


if __name__ == "__main__":
    if "--dry-run" in sys.argv:
        raise SystemExit(main())
    with Sender(environment="sandbox") as _sender:
        raise SystemExit(main(_sender))
