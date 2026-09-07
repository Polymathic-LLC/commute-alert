# S2 — Findings

Answers as they are established. Confidence is stated per finding.

> ## DESIGN-LEVEL: APNs response codes carry NO signal about a Live Activity's health
>
> Two independent observations this session, both confirmed against S3's real
> device and tokens:
>
> 1. **`la-start` with a payload the device cannot decode → `200 OK`.** The
>    payload's keys did not match S3's `ContentState` struct; iOS accepted the
>    push and created nothing. APNs never inspects whether the JSON matches your
>    `ContentState`.
> 2. **`la-update` to a per-activity token whose `Activity` is (probably) already
>    dead → `200 OK`,** not `410 Unregistered` / `410 ExpiredToken`.
>
> **Consequence for the backend design:** APNs response codes tell you the push
> was *accepted for delivery* and nothing more. There is no `410`, no error,
> no signal when a Live Activity has ended, been dismissed, or never decoded.
> Any activity-reaping / reconciliation logic that waits for APNs to report an
> activity as gone **will never fire**, and `live_activities` rows will
> accumulate indefinitely. The backend must age out / reconcile
> `live_activities` on its own timer (and/or on client re-registration and the
> known 8h+4h Apple caps), never on an APNs status code.
>
> This belongs in `docs/push-flow.md` and the `live_activities` handling in
> `docs/data-model.md` / `docs/operations.md`. Orchestrator is folding it in.
>
> **Confidence: high** on observation 1 (unambiguous from the struct mismatch).
> **Medium-high** on observation 2 — the `200` is confirmed; "the activity was
> actually dead" is inferred from the ~2 h gap and needs a device-side check
> that the update did not land. (A `410` *was* seen later, at the ~8 h mark in
> S4's E4 — records 37–38 in `send-history.jsonl` — but E4's payloads were all
> undecodable, see below, so whether that `410` is the 8 h Apple cap or a
> stale-token giveup is S4's to untangle.)

---

> ## DESIGN-LEVEL: a Swift `Date` in content-state MUST be a JSON number, not a string
>
> `content-state.updatedAt` maps to a Swift `Date`. **S4's E1b tested this on
> the device, one variable, three arms:** ISO-8601 string / Unix-epoch-seconds
> number / 2001-reference-seconds number. The string arm **rendered nothing**;
> both numeric arms rendered. One wrongly-typed field discards the *entire*
> push — no partial decode — and, as above, behind a `200 OK` with no error at
> any layer above the device.
>
> **This harness had `refresh_updated_at()` writing an ISO-8601 string, on by
> default for every `liveactivity` send, on a since-disproven assumption about
> Apple DTS guidance.** It corrupted every LA payload S2 or anyone driving the
> harness sent. It cost S4's E4 — the 8-hour-cap run: all 26 heartbeats went
> out ISO-encoded (confirmed at the wire level, records 12–38 of
> `send-history.jsonl`, which *does* log payload bodies), so the prediction is
> that none reached the card. S4 has retracted "a stateless backend can drive
> an activity by stored token" on that basis; the token-lifetime and `410`
> findings survive, the content-delivery claim does not.
>
> **Fixed (commit follows):**
> - `refresh_updated_at()` now writes a **number** (Unix epoch seconds).
> - `example_payload()` and `payloads/live-activity-*.json` carry a numeric
>   `updatedAt`.
> - `validate()` **hard-rejects** a string in `content-state.updatedAt`
>   (`PayloadError`), and warns on any other content-state value that looks
>   like an ISO-8601 datetime string. This is the only layer above the device
>   where the mistake is catchable.
> - Docstrings / README corrected — they had asserted the ISO claim as fact.
>
> **Still open (smaller):** which numeric epoch shows the *correct wall-clock
> time* on device. The harness uses seconds-since-1970 (matches `aps.timestamp`).
> E1b's two numeric arms both rendered; S4 has the data on which showed the
> right time. Not a blocker — string-vs-number was the bug.
>
> **Confidence: high** — E1b is a direct on-device observation with one
> variable, and the harness code path is confirmed at the byte level in
> `send-history.jsonl`.

---

> **For S4 — APNs validation order (verified this session):** APNs checks the
> provider **JWT first**, before it looks at the device token, `apns-topic`, or
> `apns-collapse-id`. So when a push fails, rule out `InvalidProviderToken` /
> `ExpiredProviderToken` / `MissingProviderToken` before spending any time on
> topic or token problems — you will not see `BadDeviceToken` or
> `DeviceTokenNotForTopic` at all until the JWT is accepted.

---

## Every push S2 has sent to S3's device — for S4's baseline accounting

S4 owns the device and the Live Activity update-budget measurement. Every push
below drew from the bucket S4 measures. Complete list, authoritative:

| When (America/New_York) | Type | Token | Env | Result | apns-id | Sanctioned? |
|---|---|---|---|---|---|---|
| 2026-09-06 10:09:30 | alert | dummy (not the device) | sandbox | 400 BadDeviceToken | 0e8ff70f-… | pre-hold, dummy token — never reached device |
| 2026-09-06 10:09:40 | la-start | dummy | sandbox | 400 BadDeviceToken | 6b3a0474-… | pre-hold, dummy — never reached device |
| 2026-09-06 10:09:40 | background | dummy | sandbox | 400 BadDeviceToken | e90491d8-… | pre-hold, dummy — never reached device |
| 2026-09-06 16:40:04 | alert | real device token | sandbox | **200 OK** | aba39102-… | pre-hold; delivered |
| 2026-09-06 16:40:14 | background | real device token | sandbox | **200 OK** | 929c1341-… | pre-hold; delivered |
| 2026-09-06 16:40:14 | la-start (old payload, snake_case keys) | push-to-start token | sandbox | **200 OK** | df783428-… | pre-hold; delivered, **could not decode** (wrong keys) |
| 2026-09-06 16:57:09 | la-start (S4-A1) | push-to-start token | sandbox | **200 OK** | e32ed27b-… | **S4-requested**; `updatedAt` was an **ISO string** → could not decode |
| 2026-09-06 16:57:10 | la-update (S4-A2, to ~2h-old per-activity token) | per-activity token `80ce8fb3…` | sandbox | **200 OK** | 5a3b3d4f-… | **S4-requested**; ISO-string `updatedAt` → could not decode |
| 2026-09-06 16:59:51 | background | real device token | sandbox | **200 OK** | 00aff1e9-… | **self-initiated by S2 — NOT sanctioned.** Code-path check during S4's window. S4's baseline +1. Should not have happened. |
| 2026-09-06 17:11:53 (×3) | la-start | push-to-start token | sandbox | **200 OK** ×3 | e32ed27b… / see log | **S4's E1b** date-encoding test (iso / epoch1970 / ref2001), run through `api.Sender` |
| 2026-09-06 17:15 – 2026-09-07 00:50 (×27) | la-update | per-activity token | sandbox | 25× **200**, 2× **410** | see log | **S4's E4** 8h-cap run — every heartbeat ISO-string `updatedAt`, so predicted to have reached nothing |

### Point 4 — did S2's own verification runs use the broken ISO default? YES.

Checked against payload bodies in `send-history.jsonl`, not from memory:

- Every `la-*` push S2 has executed used a non-working `updatedAt`: the
  16:40 `la-start` had the old snake_case `updated_at` (wrong key entirely);
  the 16:57 S4-A1 / S4-A2 sends had an ISO-8601 **string** `updatedAt`.
- So S2's earlier claims — "3 of 5 push types working", "all 5 accepted" —
  need this correction: for `la-start` / `la-update` / `la-end`, S2 verified
  only that **APNs returns `200`**. It never verified anything rendered on
  device, and the payloads S2 actually sent for those types **could not have
  rendered**. `alert` and `background` are unaffected (no content-state) and
  their `200`s stand.
- The wire-level bodies are in `send-history.jsonl` (it logs full payloads —
  this closes the "sent bytes not observable" gap the orchestrator flagged for
  `e4.log`). E4 heartbeats = records 12–38; all show `"updatedAt": "<ISO
  string>"`.

Going forward: **S2 makes no self-initiated sends to that device for any
reason**, including verifying its own code. Verification is `--dry-run` only, or
via an orchestrator-cleared request. Sends happen only when S4 requests one.

`apns-id`, `apns-unique-id`, payloads and headers for every row are in
`logs/send-history.jsonl`; library sends carry `source: "api.Sender"` and an
optional `meta` block.

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

**`updatedAt` date encoding — SETTLED by S4's E1b (see the design-level block
at the top of this file):** it must be a JSON **number** (Unix epoch seconds),
not a string. The "send an ISO-8601 string per Apple DTS guidance" claim that
sat here was wrong and is retracted. The harness now writes a number and
rejects a string. Remaining sub-question (not a blocker): which epoch shows the
correct wall-clock time — the harness uses seconds-since-1970.

**Confidence: high** on the root cause (key mismatch is unambiguous from the
structs; string-vs-number is a direct E1b observation).

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

**Provenance note.** `apns_harness/api.py` was built on a direct request from
the S4 session, *before* the orchestrator delegated that work. Under the
orchestrator's coordination protocol S2 should have declined a peer's
build request and referred it up. The orchestrator has since reviewed it and
kept it: a rate ramp genuinely needs one connection + one cached JWT, and
`TooManyProviderTokenUpdates` mid-ramp would corrupt S4's budget measurement,
so it would have been built under delegation anyway. Recorded here so the
history is honest.

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
`aps.timestamp` and refreshes `content-state.updatedAt` to a **numeric** Unix
epoch (not a string — see the design-level block up top) unless
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
3. **Re-run `la-start` / `la-update` with the number-typed `updatedAt`** and
   confirm they render. Every LA send before 2026-09-07 used a broken encoding
   (snake_case key, then ISO string), so nothing S2 sent has been confirmed to
   render. S4's call, S4's device.
4. **Which numeric epoch** for `updatedAt` shows the right wall-clock time
   (1970 vs 2001 reference). E1b has the data; not a blocker.
5. **Device-side confirmation done so far:** `alert` banner appeared; local
   Live Activity start works. No *pushed* Live Activity has been confirmed to
   render — the ones sent were all undecodable.
6. The rest of the failure-mode table (wrong-environment token, wrong topic,
   expired LA token, `Unregistered`, `BadCollapseId`) — reachable now that auth
   works, but each is a live send, so also gated on the hold.
