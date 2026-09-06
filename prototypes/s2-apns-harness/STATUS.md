STATUS: BLOCKED

Last updated: 2026-09-06 (session start day)
Summary: Harness is built, tested, and verified against the APNs sandbox with a
throwaway key. Every code path that does not require a real credential is done.
Blocked only on the real `.p8` + a device token to send a successful push and
document the token/topic failure modes.

## Needs from human

1. **APNs `.p8` provider key + Key ID** (day-0 ask, batchable).
   Create at developer.apple.com → Certificates, IDs & Profiles → Keys → new
   key with "Apple Push Notifications service (APNs)" enabled. Download the
   `AuthKey_XXXXXXXXXX.p8` (one-time download) and note the 10-char Key ID.
   Drop it at exactly:
     /Users/bradleybares/Git/commute-alert/prototypes/s2-apns-harness/.secrets/AuthKey_<KEYID>.p8
   And create:
     /Users/bradleybares/Git/commute-alert/prototypes/s2-apns-harness/.secrets/apns.env
   containing:
     APNS_KEY_ID=<the 10-char Key ID>
     APNS_TEAM_ID=MSQSPT8P3W          # already defaulted; only needed if different
     APNS_BUNDLE_ID=com.polymathic.commutealert.s3probe   # must equal S3's Xcode bundle id
   (`.secrets/` is gitignored. The directory does not exist yet — create it.)

2. **One device token to send to.** Any of the three S3 captures works for a
   first end-to-end check; ideally all three eventually:
     - Live Activity push-to-start token   (for `la-start`)
     - Live Activity per-activity token     (for `la-update` / `la-end`)
     - plain APNs device token              (for `alert` / `background`)
   S3 is collecting these into prototypes/s3-apple-setup/tokens.md. If that file
   can't reach this session (S3 is on its own branch), paste the tokens to the
   orchestrator and it will relay. No separate ask needed if S3's file is
   reachable.

Neither item blocks further build work — there is none left that is independent
of them. Hence BLOCKED rather than RUNNING.

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
