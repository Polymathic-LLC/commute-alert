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
| **2026-09-06 16:40:14** | **la-start** (old, undecodable payload) | **real push-to-start token** | sandbox | **200 OK** | df783428-… |
| **2026-09-06 16:57:09** | **la-start** (S4-A1, corrected payload, `routeName=S4-A1`) | push-to-start token | sandbox | **200 OK** | e32ed27b-… |
| **2026-09-06 16:57:10** | **la-update** (S4-A2, to hours-old per-activity token) | per-activity token `80ce8fb3…` | sandbox | **200 OK** | 5a3b3d4f-… |
| **2026-09-06 16:59:51** | **background** (S2 api.Sender live-path check) | real device token | sandbox | **200 OK** | 00aff1e9-… |

Hold lifted 2026-09-06 ~16:55 by S4 (s4-live-activity), which now owns the
device and coordinates all live sends. The 10:09 rows never reached the device
(dummy tokens). Everything from 16:40 on was accepted for delivery. `apns-id`,
`apns-unique-id`, payloads and headers for every row are in
`logs/send-history.jsonl`; sends from the library entry point carry
`source: "api.Sender"` and an optional `meta` block.

**Data point — `la-update` to a stale per-activity token (S4-A2):** the
per-activity token was captured ~2 h before this send and its `Activity` may
already be dead on-device. APNs still returned **`200 OK`**, not `410
Unregistered` or `410 ExpiredToken`. So a `200` on an LA update does **not**
prove the activity is alive — APNs accepts it and (presumably) drops it if the
activity is gone. S4: whether the update actually applied is a device-side read.

**Sequencing lesson (not repeated):** S2 sent the `la-start` push-to-start
*before* S3 confirmed that a Live Activity can be started **locally** on the
device. The plan wanted local-start first precisely so an ActivityKit failure
is distinguishable from an APNs failure. For any future first contact with a new
device: local start, confirm it renders, *then* push.

---

## Q: `la-start` returned 200 but no Live Activity appeared. Why?

**Answer: the push payload's `attributes` / `content-state` keys did not match
S3's Swift structs, so iOS accepted the push and silently decoded nothing.**
Fixed in this session.

Disambiguation (2026-09-06 evening): the user confirmed a **local** start puts a
Live Activity on the lock screen, and the `alert` push produced a visible
banner. So ActivityKit works on the device and APNs delivery works. The failure
was specific to the push-to-start *payload*.

Root cause — the first `la-start` (16:40) sent invented placeholder keys:

| Sent | S3's actual struct (`Sources/Shared/CommuteActivityAttributes.swift`) |
|---|---|
| `attributes: {route_id, stop_id, direction_id, window_label}` | `CommuteActivityAttributes { routeName: String; stopName: String }` |
| `content-state: {display_status, updated_at}` | `ContentState { v: Int; displayStatus: String; headline: String; minutesToDeparture: Int?; updatedAt: Date }` |

ActivityKit's push JSONDecoder does **not** apply `.convertFromSnakeCase` and
does not tolerate missing non-optional keys, so `displayStatus` / `updatedAt` /
`routeName` were absent → decode failed → `Activity` never created. APNs had
already returned `200` because the payload is well-formed *JSON*; APNs never
looks at whether it matches your `ContentState`.

Fix applied: `payloads/live-activity-*.json` and `example_payload()` now use
S3's exact keys (`routeName`, `stopName`, `displayStatus`, `minutesToDeparture`,
`updatedAt`). A unit test (`test_la_example_payloads_match_s3_struct_keys`)
guards against regressing to snake_case.

**Unverified:** the corrected payload has NOT been sent (live-send hold). S4
should send it first and confirm the Live Activity actually starts.

**`updatedAt` date encoding is still open.** It is a Swift `Date`. The corrected
payload sends an ISO-8601 string (`"2026-09-06T20:48:49Z"`), per Apple DTS
guidance that ActivityKit's push decoder uses `.iso8601`. This is unconfirmed
for this struct. If S4 sees the activity start but `updatedAt`-dependent UI not
update, try: Unix epoch seconds as a number, then `.deferredToDate` (seconds
since 2001). The harness auto-refreshes `content-state.updatedAt` to now on
every LA send (`--keep-updated-at` to disable); `aps.timestamp` (a separate
envelope field, always Unix seconds) is injected too.

**Confidence: high** on the root cause (key mismatch is unambiguous from the
structs). **Medium** that the ISO-8601 date form is right — flagged for S4.

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
| `la-start` (push-to-start) | push-to-start token (160-hex) | **`200 OK`** (but decoded nothing on-device — see below) |
| `la-update` | per-activity token (160-hex, now captured) | not sent — live-send hold |
| `la-end` | per-activity token | not sent — live-send hold |

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
| `la-update` to a ~2h-old per-activity token (activity maybe dead) | — | **observed: `200 OK`**, not 410. A `200` on an LA update does not prove the activity is live. |
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

## Driving the harness at rate (for S4)

**Connection + token reuse.** `client.ApnsClient` holds one `httpx.Client(http2=True)`
for its lifetime — sends on one instance reuse the pooled HTTP/2 connection (TLS
negotiated once). `jwt_auth.ProviderTokenSigner` mints the provider JWT once and
reuses it for 45 min (`REFRESH_AFTER_SECONDS`), re-signing under a lock only when
stale. So a long in-process loop will **not** renegotiate TLS per send and
**cannot** trip `TooManyProviderTokenUpdates` — *provided you reuse one sender*.
The CLI builds a fresh `ApnsClient` + signer per invocation, so a
subprocess-per-send loop is the wrong way to drive a ramp (new connection and a
newly-minted token every send).

**Library entry point:** `apns_harness/api.py`.

```python
from apns_harness.api import Sender
from apns_harness.payloads import example_payload

with Sender(environment="sandbox") as s:      # one client, one signer, for the whole ramp
    for i in range(n):
        resp = s.send(
            type="la-update",                  # "la-update" | "la-start" | "la-end" | "alert" | "background"
            token=per_activity_token,
            payload=example_payload("la-update"),   # a dict; deep-copied, never mutated
            headline=f"ramp {i}",              # convenience: overwrites aps.content-state.headline
            collapse_id="ramp",                # optional
            ttl=3600,                          # optional; sets apns-expiration = now + ttl
            extra_log={"seq": i, "phase": "A"},# optional; lands in send-history.jsonl under "meta"
        )
        # resp: ApnsResponse — .status_code .reason .ok .apns_id .apns_unique_id .timestamp .hint() .as_dict()
```

`s.send_detailed(...)` returns `(BuiltRequest, ApnsResponse, record)` if you also
want the exact headers. `s.sent` counts sends; `s.provider_token_refreshes`
should stay at `1` across a whole ramp — watch it. Every send writes to the same
`logs/send-history.jsonl` the CLI uses, tagged `source: "api.Sender"`. Pass
`log=False` on a call to skip that. `Sender.send` for `la-*` also injects a fresh
`aps.timestamp` and refreshes `content-state.updatedAt` (ISO-8601) unless
`refresh_la_fields=False`.

Verified live 2026-09-06 16:59:51 EDT: one `background` send through `Sender`
→ `200 OK`, `provider_token_refreshes == 1`, logged. The CLI's own send path was
refactored to go through `Sender`, so CLI and library are one code path.

**Note for the budget numbers:** the probe app's Info.plist sets
`NSSupportsLiveActivitiesFrequentUpdates = true`. Any ceiling S4 measures is the
*frequent-updates* ceiling, not the default one.

---

## Still open

**Live sends resume under S4's coordination** (hold lifted 2026-09-06 ~16:55).
S2 is the send mechanism; S4 designs the experiment and owns the device.

1. ~~A `200 OK` on a valid provider token.~~ **Done** — alert, background,
   la-start (2026-09-06 16:40 EDT).
2. ~~Capture all three device tokens.~~ **Done** — push-to-start, per-activity,
   and APNs device token all in S3's `tokens.md`.
3. **Send the *corrected* `la-start`** and confirm it actually starts a Live
   Activity (the first one didn't — key mismatch, now fixed). Then `la-update` /
   `la-end`. All gated on the live-send hold; S4's call.
4. **`updatedAt` date encoding** — corrected payload uses ISO-8601; unconfirmed
   for this struct. S4 to verify; fallbacks noted above.
5. **Device-side confirmation done so far:** `alert` banner appeared; local
   Live Activity start works; push-to-start with the *old* payload started
   nothing.
6. The rest of the failure-mode table (wrong-environment token, wrong topic,
   expired LA token, `Unregistered`, `BadCollapseId`) — reachable now that auth
   works, but each is a live send, so also gated on the hold.
