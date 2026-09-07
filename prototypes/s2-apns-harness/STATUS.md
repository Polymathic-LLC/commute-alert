STATUS: RUNNING (active — send path for S4)

Last updated: 2026-09-07 (night — fixed the updatedAt string-vs-number defect)
Summary: Harness is the mechanical send path for S4. Every LA push before
2026-09-07 carried a broken `content-state.updatedAt` — first the old
snake_case key, then (default-on) an ISO-8601 **string**. S4's E1b proved on
device that a Swift `Date` needs a JSON **number**; a string discards the whole
push behind a `200 OK`. That default cost S4's E4 (the 8h-cap run). **Fixed:**
`refresh_updated_at` writes a number, example payloads are numeric, `validate()`
hard-rejects a string in a Date field, docstrings/README corrected. 44 tests.

S2's role, per the orchestrator: **mechanical send path for S4 only.** No
feature-building / scope changes / self-initiated sends on a peer's say-so;
verification is `--dry-run` only. All status / findings / asks via the
orchestrator.

Key findings folded up (going into docs):
- **APNs response codes carry no signal about a Live Activity's health** — 200
  on an undecodable payload, 200 on a dead-activity token; `410` only seen at
  the ~8h cap (with the E4 ISO confound). Backend reaping must use its own
  timer, never an APNs status code.
- **content-state Swift `Date` must be a JSON number, not a string** (E1b).

Corrections on record:
- The 16:59:51 background send was self-initiated by S2 during S4's window —
  S4 baseline +1; no self-initiated sends since.
- S2's earlier "3 of 5 working / all 5 accepted": for `la-*` only APNs-`200`
  was ever verified; the payloads S2 sent could not have rendered. `alert` /
  `background` `200`s stand.

## Needs from human / S3 / orchestrator

1. ~~APNs `.p8` provider key~~ **DONE** (Key ID `42H763JTRN`).
2. ~~Per-activity push token~~ **DONE** — all three tokens in S3's tokens.md.
3. ~~Lift the live-send hold~~ **DONE** — S4 owns it.

Outstanding (device-side, S4 with the phone):
- Do `la-start` / `la-update` with the **number-typed** `updatedAt` render?
  Nothing S2 has sent has been confirmed to render.
- Which numeric epoch for `updatedAt` — **S2 writes 1970, S4's script writes
  2001-reference.** They diverge; S4's E0 calibration settles it. S2 keeps 1970
  flagged as unresolved and aligns when E0 reports (orchestrator relays). Not
  changing it on a guess.

Pre-send safety added this round: `payloads.check_fatal_shapes()` runs on every
send, cannot be disabled, hard-raises on the two shapes proven fatal today
(string in a `Date` field; snake_case keys). New fatal shapes append here.

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
  (NOTE: built on a peer request ahead of orchestrator delegation — reviewed
  and kept. Provenance in FINDINGS.md.)
- **2026-09-07 — `updatedAt` string-vs-number defect (orchestrator-routed).**
  The `refresh_updated_at` I added above wrote an ISO-8601 **string**, default
  on. S4's E1b proved on device: a Swift `Date` needs a JSON **number**; a
  string discards the whole push behind a 200. It corrupted every LA send,
  including S4's E4 8h-cap run (26 heartbeats, all ISO — confirmed at the wire
  level in send-history.jsonl). Fixed: `refresh_updated_at` → number;
  `example_payload()` + `payloads/*.json` numeric; `validate()` hard-rejects a
  string in a Date field + warns on ISO-looking strings; docstrings/README
  corrected. Answered orchestrator point 4: yes, S2's own LA verification sends
  all used the broken encoding — for `la-*`, only APNs-200 was ever verified.
  44 tests.
