STATUS: RUNNING (idle — awaiting orchestrator direction)

Last updated: 2026-09-06 (day 0, night — orchestrator corrective protocol received)
Summary: All 5 push types have been accepted by APNs (`200 OK`) against the
sandbox with S3's real tokens. `apns_harness/api.py` (`Sender`) is in place as
the loop entry point; CLI routes through it; 42 tests pass. The harness is
functionally complete.

Orchestrator issued a corrective protocol: all coordination and human asks go
through the orchestrator, not peer sessions or the user; S2 does not build
features or negotiate scope on peer request. S2 acted on S4's direct requests
(2 baseline sends + a verification send + building `api.py`) *before* that
message landed — reported to the orchestrator. Now idle: no sends, no new work,
until the orchestrator directs. S2 remains the mechanical send path when the
orchestrator delegates a send.

## Needs from human / S3 / orchestrator

1. ~~APNs `.p8` provider key~~ **DONE** (Key ID `42H763JTRN`).
2. ~~Per-activity push token~~ **DONE** — all three tokens in S3's tokens.md.
3. ~~Lift the live-send hold~~ **DONE** — S4 owns it now.

Outstanding (device-side reads, S4 to gather when watching the phone):
- Does the **corrected** `la-start` (sent 16:57 as S4-A1) actually put a Live
  Activity on the lock screen? (the pre-fix one didn't.)
- Does `updatedAt` as ISO-8601 decode into the Swift `Date`? Fallbacks in
  FINDINGS if not.
- Did the `la-update` to the ~2h-old per-activity token (S4-A2, `200 OK`)
  actually change anything on-screen, or was it silently dropped?

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
- User: `alert` banner arrived; `la-start` started no Live Activity; local
  start works; per-activity token added. Read S3's Swift structs and found the
  `la-start` payload used invented snake_case keys (`route_id`, `display_status`,
  `updated_at`) instead of S3's `routeName` / `displayStatus` / `updatedAt` etc.
  → iOS decoded nothing. Fixed the LA payloads + `example_payload()`; added
  `refresh_updated_at` (ISO-8601) alongside `inject_timestamp`; regression test.
  Date-encoding strategy for `updatedAt` still unverified — flagged for S4.
- S4 (s4-live-activity) took the device + hold, lifted the hold, and asked for
  two baseline sends. Sent 16:57 EDT: la-start S4-A1 (corrected payload) → 200;
  la-update S4-A2 to the ~2h-old per-activity token → **200** (not 410
  Unregistered — a real failure-table data point: a 200 on an LA update does
  not prove the activity is alive).
- Built `apns_harness/api.py` (`Sender`) as S4's loop entry point: one
  `ApnsClient` + one `ProviderTokenSigner` per instance (connection + JWT
  reuse, no `TooManyProviderTokenUpdates`), deep-copies payloads, logs to the
  canonical history with `source`/`meta` tags. Refactored `cmd_send` to use it.
  Verified live (background → 200, 1 token refresh). +7 tests, 42 total.
