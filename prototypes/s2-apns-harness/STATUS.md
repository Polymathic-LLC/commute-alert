STATUS: RUNNING (live-send hold in effect)

Last updated: 2026-09-06 (day 0, evening — first real 200s, then send hold)
Summary: 3 of 5 push types sent successfully to S3's real device — `alert`,
`background`, `la-start` (push-to-start) → `200 OK` from the APNs sandbox.
Then the orchestrator put S2 on a **live-send hold**: no more pushes to that
device until S4 (which owns the Live Activity update-budget measurement)
coordinates, so its budget baseline isn't drawn down by uninstrumented S2
traffic. Remaining `la-update` / `la-end` work continues as dry-run + payload
validation only. All traffic S2 has sent is logged in FINDINGS.md with
timestamps for S4 to subtract.

## Needs from human / S3 / orchestrator

1. ~~APNs `.p8` provider key~~ **DONE** (Key ID `42H763JTRN`).

2. **Orchestrator/S4: lift the live-send hold** when S4 is ready to own the
   device, so `la-update` / `la-end` and the failure-mode catalogue can be sent
   for real. S2 is the send mechanism; S4 is the experiment designer.

3. **Per-activity push token** — still the only unfilled row in S3's tokens.md.
   S3: tap "① Start locally" in the probe app, copy the `LIVE ACTIVITY
   per-activity push token`, paste it in. Needed before `la-update` / `la-end`
   can be sent (dry-run already validates the shape). No rush given (2).

4. **Device-side confirmation** (S3/S4, quick): did the `la-start` push put a
   Live Activity on the lock screen? Did the `alert` banner appear? A `200`
   only means APNs accepted it.

## Blocked-command log (background-session permission prompts)

(none)

## Activity log

- Read DERISKING.md (S2) and docs/push-flow.md from the main checkout.
- Entered git worktree `worktree-s2-apns-harness`.
- Built `apns_harness/` package: config + S3-probe defaults, ES256 JWT signing
  with caching, HTTP/2 APNs client with reason-code hints, payload table +
  validation for all 5 push shapes, S3 token-file reader, append-only send
  history, CLI (`doctor`, `example`, `send`, `history`, `jwt`).
- Adopted the orchestrator's canonical secret paths and the authoritative
  S3-probe identifiers (team MSQSPT8P3W, bundle com.polymathic.commutealert.s3probe).
- Made credential + token paths resolve to the MAIN checkout when running in a
  worktree.
- 29 unit tests pass (`.venv/bin/python -m pytest -q`).
- Probed the APNs sandbox with a locally-generated throwaway key: confirmed
  HTTP/2 transport, ES256 JWT is well-formed (Apple returns
  `403 InvalidProviderToken`, and `MissingProviderToken` with no auth header),
  and HTTP/1.1 is rejected at the protocol level. See FINDINGS.md.
- Deleted the throwaway key and probe log (never committed).
- Orchestrator review: rebuilt the S3 token reader to S3's actual format (label
  then token on the NEXT line, inside a fenced block) instead of the assumed
  bullet / key:value layout. Verified against the orchestrator's dummy-filled
  template: all three tokens extract to the right roles; the "activity"
  substring in the push-to-start label does not collide; an unfilled
  `<paste …>` placeholder raises a loud error. +4 unit tests (33 total).
- Added an APNs validation-order callout to the top of FINDINGS.md for S4.
- Real `.p8` arrived (Key ID 42H763JTRN). `doctor` green; JWT signs. Verified
  end to end vs sandbox: `alert` / `la-start` / `background` to a bogus token
  return `400 BadDeviceToken` (was `403 InvalidProviderToken`) — auth + topic ok.
- S3 filled tokens.md (in the S3 worktree) with push-to-start + APNs device
  tokens. Extended the token reader to auto-discover S3's file in any worktree,
  and fixed placeholder detection so an unfilled row isn't masked by the next
  row's hex. 33 tests pass.
- Sent for real vs sandbox: `alert` → 200, `background` → 200, `la-start` → 200.
  All carried both `apns-id` and `apns-unique-id` (sandbox does return the
  latter — corrected in FINDINGS.md). `la-update` / `la-end` await the
  per-activity token.
- Orchestrator called a **live-send hold**: S2's uninstrumented sends draw down
  the Live Activity budget bucket S4 exists to measure. No more sends to the
  device without S4 coordination; remaining work is dry-run only. Logged all
  sent traffic (3× 200 at 16:40, 3× 400 at 10:09) in FINDINGS.md for S4 to
  subtract, plus a sequencing lesson (push-to-start was sent before S3's
  local-start pass/fail was confirmed) and the canonical tokens.md path gap.
