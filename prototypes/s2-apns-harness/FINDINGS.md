# S2 — Findings

Answers as they are established. Confidence is stated per finding.

> **For S4 — APNs validation order (verified this session):** APNs checks the
> provider **JWT first**, before it looks at the device token, `apns-topic`, or
> `apns-collapse-id`. So when a push fails, rule out `InvalidProviderToken` /
> `ExpiredProviderToken` / `MissingProviderToken` before spending any time on
> topic or token problems — you will not see `BadDeviceToken` or
> `DeviceTokenNotForTopic` at all until the JWT is accepted.

---

## Push traffic S2 has sent to S3's device — subtract this from any budget baseline

Per the orchestrator: the Live Activity update budget is S4's central unknown,
and every push to the device draws from a bucket S4 has not characterized. S2
has stopped sending and will not send again to that device without S4/orchestrator
coordination. Everything S2 sent, so S4 can account for it:

| When (America/New_York) | Type | Token | Env | Result | apns-id |
|---|---|---|---|---|---|
| 2026-09-06 10:09:30 | alert | dummy (not the device) | sandbox | 400 BadDeviceToken | 0e8ff70f-… |
| 2026-09-06 10:09:40 | la-start | dummy | sandbox | 400 BadDeviceToken | 6b3a0474-… |
| 2026-09-06 10:09:40 | background | dummy | sandbox | 400 BadDeviceToken | e90491d8-… |
| **2026-09-06 16:40:04** | **alert** | **real device token** | sandbox | **200 OK** | aba39102-… |
| **2026-09-06 16:40:14** | **background** | **real device token** | sandbox | **200 OK** | 929c1341-… |
| **2026-09-06 16:40:14** | **la-start** | **real push-to-start token** | sandbox | **200 OK** | df783428-… |

The three 10:09 rows never reached the device (dummy tokens, rejected pre-delivery)
— they cost nothing on the device. The three 16:40 rows were accepted for
delivery to the real device. No `la-update` / `la-end` has ever been sent.
Full detail (payloads, headers, `apns-unique-id`) in `logs/send-history.jsonl`.

**Sequencing lesson (not repeated):** S2 sent the `la-start` push-to-start
*before* S3 confirmed that a Live Activity can be started **locally** on the
device. The plan wanted local-start first precisely so an ActivityKit failure
is distinguishable from an APNs failure. Push-to-start returning `200` is
strictly more informative than a local start, but if the device shows nothing
we cannot now tell which layer broke. For any future first contact with a new
device: local start, confirm it renders, *then* push.

---

## Q: Does the tool build against placeholders before credentials arrive?

**Answer: Yes.** The full harness — JWT signing, HTTP/2 client, all five push
shapes, payload validation, send history, CLI — is complete and exercised
without a real `.p8`. `--dry-run` prints the exact request (URL, headers, body,
equivalent curl) with no credentials or network. 33 unit tests pass.

**Confidence: high.** Verified in this session.

---

## Q: Does `.p8` provider-token (JWT) auth work end to end against the sandbox?

**Answer: Yes — confirmed with `200 OK` on real device tokens.** Key ID
`42H763JTRN`, team `MSQSPT8P3W`, topic `com.polymathic.commutealert.s3probe`.

Sends against `https://api.sandbox.push.apple.com` with S3's real tokens:

| Push type | Token | Result |
|---|---|---|
| `alert` | APNs device token (64-hex) | **`200 OK`** |
| `background` | APNs device token (64-hex) | **`200 OK`** |
| `la-start` (push-to-start) | push-to-start token (160-hex) | **`200 OK`** |
| `la-update` | per-activity token | not yet — token still a placeholder in S3's file |
| `la-end` | per-activity token | not yet — same |

Earlier auth-progression evidence (documents the failure ladder):

- Throwaway P-256 key (unknown `kid`): **`403 InvalidProviderToken`**.
- No `authorization` header: **`403 MissingProviderToken`**.
- Real key, **bogus** device token: **`400 BadDeviceToken`** (alert / la-start /
  background) — past auth and topic, stops at the token.
- HTTP/1.1: `RemoteProtocolError: illegal request line` — APNs refuses at the
  protocol level. **HTTP/2 is mandatory**, confirmed. `httpx[http2]` (h2 4.x)
  negotiates it fine.

**Confidence: high** for the three `200`s (accepted for delivery). Whether the
push-to-start Live Activity actually *rendered* on the lock screen is a
device-side observation for S3/S4, not visible from the APNs response.

---

## Q: Does the sandbox return `apns-unique-id`?

**Answer: Yes.** Every `200 OK` from `api.sandbox.push.apple.com` this session
carried both `apns-id` (our UUID, echoed) and a distinct `apns-unique-id`
(APNs-assigned, e.g. `44fedd3f-2ddc-89d3-437b-bf97edc74e68`). Earlier this doc
listed `apns-unique-id` as possibly prod-only — that was wrong; sandbox returns
it. Both are logged in `send-history.jsonl`, so S4 can correlate on either.

**Confidence: high.** Observed on all three successful sends.

---

## Q: What does APNs return for a stale / wrong Live Activity token, wrong
topic, oversized collapse-id, etc.?

**Answer: Partly observed. Auth + malformed-token confirmed; the rest still
needs a *real* device token to reach.**

APNs validates the JWT first, then the topic, then the device token. With the
throwaway key everything returned `InvalidProviderToken`; with the real key, a
malformed device token returns **`400 BadDeviceToken`** (observed, all push
types). The rows below marked "observed" are confirmed this session; the rest
need a real token from S3 to exercise (a well-formed token pointed at the wrong
environment, an expired LA token, etc.):

| Condition | `reason` (HTTP) | Status |
|---|---|---|
| Malformed / unknown device token | `BadDeviceToken` (400) | **observed** (alert, la-start, background) |
| JWT signed with unknown key | `InvalidProviderToken` (403) | **observed** |
| No `authorization` header | `MissingProviderToken` (403) | **observed** |
| Well-formed token, wrong environment (sandbox vs prod) | `BadDeviceToken` (400) | needs real token |
| LA token valid but wrong `apns-topic` | `DeviceTokenNotForTopic` (400) | needs real token — the `.push-type.liveactivity` suffix mistake |
| Topic not permitted for the key | `TopicDisallowed` (400) | needs real token — key not enabled for the app / capability |
| LA token expired | `ExpiredToken` (410) | needs real token — LA per-activity tokens rotate |
| Activity ended / app uninstalled | `Unregistered` (410) | needs real token — includes a `timestamp` in the body |
| JWT older than 1h | `ExpiredProviderToken` (403) | from Apple ref — our signer refreshes at 45min to avoid this |
| JWT refreshed too often | `TooManyProviderTokenUpdates` (429) | from Apple ref — our signer caches, so a run won't trip this |
| `apns-collapse-id` > 64 bytes | `BadCollapseId` (400) | needs real token (collapse-id is checked after the token) |
| payload > 4KB | `PayloadTooLarge` (413) | harness rejects locally before sending |

The harness maps all of these to a one-line hint in its output
(`client.REASON_HINTS`).

**Confidence: high** for the "observed" rows. The rest wait on a real device
token from S3 — the validation order (JWT → topic → token → collapse-id) means
they can't be reached with a bogus token.

---

## Q: Which host / topic does each push type use?

**Answer (implemented and unit-tested):**

- Hosts: `api.sandbox.push.apple.com` / `api.push.apple.com`, path
  `/3/device/<token>`.
- Live Activity (update, push-to-start, end): `apns-push-type: liveactivity`,
  `apns-topic: <bundle-id>.push-type.liveactivity`, priority 10. Push-to-start
  and per-activity updates use the **same** topic; they differ only by which
  token you send to and by `aps.event` (`start` vs `update`) + the
  `attributes` / `attributes-type` keys on `start`.
- Alert: `apns-push-type: alert`, `apns-topic: <bundle-id>`, priority 10.
- Background/widget: `apns-push-type: background`, `apns-topic: <bundle-id>`,
  priority 5, body `{"aps":{"content-available":1}}`.

`<bundle-id>` for the probe is `com.polymathic.commutealert.s3probe` (from the
orchestrator; overridable via `APNS_BUNDLE_ID`). Team ID `MSQSPT8P3W`.

**Confidence: high** for structure; the bundle id must still be reconciled
against S3's actual Xcode project.

---

## Q: `aps.timestamp` handling for Live Activity

**Answer:** committed example payloads deliberately omit it; the sender injects
`int(time.time())` on every LA send unless the payload already carries one.
Apple orders LA updates by `aps.timestamp`, so a stale committed value would
cause silently-dropped updates. `--dismissal-in` / `--dismissal-date` add
`aps.dismissal-date` to `la-end` at send time.

**Confidence: high** (implementation); the drop-on-stale-timestamp behavior
itself is S4's to measure.

---

## Q: Can the harness read S3's token handoff file?

**Answer: Yes, verified against S3's real template format.**

S3 does not use bullets or `key: value` — it writes a `## Tokens` section with a
fenced code block, each token on the line **after** its label:

```
LIVE ACTIVITY push-to-start token:
<hex>

LIVE ACTIVITY per-activity push token:
<hex>

APNs device token (alert / background):
<hex>
```

The reader was tested against S3's filled-with-dummy-hex template and extracts
all three, to the correct roles. Specific hazards checked:

- Token on the following line, not the label line — handled.
- Blank lines and ` ``` ` fence lines between label and token — skipped.
- The push-to-start label contains the substring "activity" — does **not**
  collide with the per-activity role, because each label line is matched to
  exactly one role, S3-exact labels first, most-specific first.
- An unfilled `<paste …>` placeholder produces a **loud** `TokenFileError`
  ("not filled in yet"), never a silent empty result.

**Confidence: high.** Verified this session against
`tokens-dummy.md` supplied by the orchestrator; 6 dedicated unit tests. Also
verified against S3's actual filled file (push-to-start + device tokens
extracted, per-activity correctly flagged as an unfilled placeholder).

### Canonical-path gap — for whoever merges S3

S3's runbook and template both say the tokens go to
`/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md`
(main checkout). **That file was never created there.** S3 filled the copy
inside its own worktree
(`.claude/worktrees/s3-apple-setup/prototypes/s3-apple-setup/tokens.md`).

S2 works around this: the reader now globs
`.claude/worktrees/*/prototypes/s3-apple-setup/tokens.md` (newest mtime first)
in addition to the main-checkout path and `$S3_TOKENS_FILE`. That is a
workaround, not a fix — when S3 is merged, the real file needs to land at the
canonical main-checkout path (it is git-ignored, so the merge alone will not
put it there; someone must copy it), or S4 must be told to use the worktree
path / env var explicitly.

---

## Still open

**S2 is on a live-send hold** (orchestrator): no more pushes of any type to
S3's device without S4/orchestrator coordination, so S4's Live Activity update
budget is measured against an untouched-by-us bucket. Remaining `la-update` /
`la-end` work is dry-run + payload validation only until then.

1. ~~A `200 OK` on a valid provider token.~~ **Done** — alert, background,
   la-start (2026-09-06 16:40 EDT).
2. **`la-update` and `la-end`** — two blockers: (a) the per-activity push token
   is still a placeholder in S3's `tokens.md`; (b) even with it, the actual
   send waits on the hold being lifted. Payload shape + headers for both are
   already verified by `--dry-run` and unit tests.
3. **Device-side confirmation.** A `200` means APNs accepted the push, not that
   anything showed. Whether the `la-start` put a Live Activity on the lock
   screen, and whether the `alert` banner appeared — S3/S4 observations.
4. The rest of the failure-mode table (wrong-environment token, wrong topic,
   expired LA token, `Unregistered`, `BadCollapseId`) — reachable now that auth
   works, but each needs a real token deliberately broken in that one way, and
   each is a live send, so also gated on the hold.
