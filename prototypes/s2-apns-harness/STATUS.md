STATUS: BLOCKED

Last updated: 2026-09-06 (day 0, after .p8 arrived)
Summary: Harness is built, tested (33 unit tests), and now verified END TO END
against the APNs sandbox with the REAL key — `.p8` auth works, the
`com.polymathic.commutealert.s3probe` topic is accepted, and a bogus device
token gets `400 BadDeviceToken` (i.e. we're past auth and topic). The ONLY
remaining blocker is a real device token, which is S3's deliverable.

## Needs from human

1. ~~APNs `.p8` provider key + Key ID~~ **DONE.** Key ID `42H763JTRN`, team
   `MSQSPT8P3W`, in `.secrets/` in the main checkout. `doctor` is green;
   `.p8` auth verified against the sandbox.

2. **A device token from S3** — the last blocker. It is not something this
   session can fetch: a device token is issued by iOS to the S3 app running on a
   physical iPhone. It comes out of S3's runbook
   (`prototypes/s3-apple-setup/RUNBOOK.md`, branch `worktree-s3-apple-setup`),
   a ~30–45 min hands-on Xcode + iPhone session that ends with three tokens
   pasted into:
     /Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md
   The three:
     - LIVE ACTIVITY push-to-start token      -> S2 `la-start`
     - LIVE ACTIVITY per-activity push token  -> S2 `la-update` / `la-end`
     - APNs device token (alert / background) -> S2 `alert` / `background`
   Once that file exists this session's reader picks it up automatically
   (verified against S3's format). For a first check, even just the
   `APNs device token` row is enough to get a real `200` on `alert`.

No independent build work remains. Hence BLOCKED.

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
  now return `400 BadDeviceToken` (was `403 InvalidProviderToken` with the
  throwaway key) — auth + topic accepted. FINDINGS.md updated. Only a real
  device token (S3) remains.
