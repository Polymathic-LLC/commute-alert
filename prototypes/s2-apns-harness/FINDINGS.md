# S2 — Findings

Answers as they are established. Confidence is stated per finding.

> **For S4 — APNs validation order (verified this session):** APNs checks the
> provider **JWT first**, before it looks at the device token, `apns-topic`, or
> `apns-collapse-id`. So when a push fails, rule out `InvalidProviderToken` /
> `ExpiredProviderToken` / `MissingProviderToken` before spending any time on
> topic or token problems — you will not see `BadDeviceToken` or
> `DeviceTokenNotForTopic` at all until the JWT is accepted.

---

## Q: Does the tool build against placeholders before credentials arrive?

**Answer: Yes.** The full harness — JWT signing, HTTP/2 client, all five push
shapes, payload validation, send history, CLI — is complete and exercised
without a real `.p8`. `--dry-run` prints the exact request (URL, headers, body,
equivalent curl) with no credentials or network. 33 unit tests pass.

**Confidence: high.** Verified in this session.

---

## Q: Does `.p8` provider-token (JWT) auth work end to end against the sandbox?

**Answer: Yes.** With the real key (Key ID `42H763JTRN`, team `MSQSPT8P3W`),
APNs accepts the JWT and the `com.polymathic.commutealert.s3probe` topic. A send
to a **bogus** device token now returns **`400 BadDeviceToken`** — not the
`403 InvalidProviderToken` we got with the throwaway key. The failure moved past
auth and past topic validation to the device token, which is exactly the
progression that proves auth works. Same result for `la-start` and `background`.
The only thing between here and a `200` is a real device token.

Evidence, all against `https://api.sandbox.push.apple.com`:

- Throwaway P-256 key (unknown `kid`): **`403 InvalidProviderToken`**.
- No `authorization` header: **`403 MissingProviderToken`**.
- **Real key**, bogus device token, `alert` / `la-start` / `background`:
  **`400 BadDeviceToken`** for all three.
- Over **HTTP/1.1**: `RemoteProtocolError: illegal request line` — APNs refuses
  at the protocol level. **HTTP/2 is mandatory**, confirmed, not just
  documented. `httpx[http2]` (h2 4.x) negotiates HTTP/2 fine.

**Confidence: high.** `.p8` auth + topic handling verified end to end this
session. `200 OK` still needs a real device token (S3).

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
`tokens-dummy.md` supplied by the orchestrator; 6 dedicated unit tests.

---

## Still open (needs the real `.p8`, Key ID, Team ID, bundle id + a device token)

1. A `200 OK` on a valid provider token.
2. The token/topic failure-mode table above, observed rather than cited.
3. End-to-end delivery of each of the five push types to a real device
   (coordinate with S3/S4 for tokens) — the DERISKING "done when" bar.
4. Whether sandbox `apns-id` correlation is enough for S4, or S4 also needs the
   `apns-unique-id` (only returned by the production environment).
