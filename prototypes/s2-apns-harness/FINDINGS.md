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

**Answer: The transport and signing path is confirmed working; final
confirmation of a *valid* key is blocked on the human's `.p8`.**

Evidence, all against `https://api.sandbox.push.apple.com` this session:

- With an ES256 JWT signed by a locally-generated P-256 key (valid structure,
  `kid` Apple does not recognise): APNs replies **`403 InvalidProviderToken`**,
  body `{"reason":"InvalidProviderToken"}`. This proves the JWT is well-formed
  enough for Apple to parse the header, look up the `kid`, and reject it — i.e.
  PyJWT ES256 signing + our header/claims shape are correct.
- With **no** `authorization` header: **`403 MissingProviderToken`**.
- Over **HTTP/1.1**: `RemoteProtocolError: illegal request line` — APNs refuses
  at the protocol level. **HTTP/2 is mandatory**, confirmed, not just
  documented. `httpx[http2]` (h2 4.x) negotiates HTTP/2 fine.

What remains for the real key: a `200` on a valid JWT, and the token/topic
failure catalogue below.

**Confidence: high** for transport/signing; the "valid key returns 200" step is
**untested, blocked on human**.

---

## Q: What does APNs return for a stale / wrong Live Activity token, wrong
topic, oversized collapse-id, etc.?

**Answer: Cannot be observed yet — provider-token validation happens first.**

APNs validates the JWT before it looks at the device token, `apns-topic`, or
`apns-collapse-id`. Every malformed-token / wrong-topic / 80-byte-collapse-id
probe this session returned `InvalidProviderToken`, because the throwaway key is
not a real one. So the following are **documented from Apple's reference, not yet
observed**, and need the real `.p8` to confirm:

| Condition | Expected `reason` (HTTP) | Notes |
|---|---|---|
| Device/LA token doesn't match env | `BadDeviceToken` (400) | sandbox vs prod host mismatch also lands here |
| LA token valid but wrong `apns-topic` | `DeviceTokenNotForTopic` (400) | the `.push-type.liveactivity` suffix mistake |
| Topic not permitted for the key | `TopicDisallowed` (400) | key not enabled for the app / capability |
| LA token expired | `ExpiredToken` (410) | LA per-activity tokens rotate |
| Activity ended / app uninstalled | `Unregistered` (410) | includes a `timestamp` in the body |
| JWT older than 1h | `ExpiredProviderToken` (403) | our signer refreshes at 45min to avoid this |
| JWT refreshed too often | `TooManyProviderTokenUpdates` (429) | our signer caches, so a run won't trip this |
| `apns-collapse-id` > 64 bytes | `BadCollapseId` (400) | |
| payload > 4KB | `PayloadTooLarge` (413) | harness rejects locally before sending |

The harness maps all of these to a one-line hint in its output
(`client.REASON_HINTS`).

**Confidence: high** that JWT-first ordering blocks local observation;
**the table itself is unverified** pending the real key.

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
