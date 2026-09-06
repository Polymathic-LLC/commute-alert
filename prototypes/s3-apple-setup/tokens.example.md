# S3 tokens — TEMPLATE

Fill this in **in the MAIN checkout**, not this worktree copy:

    cp /Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.example.md \
       /Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md

Then paste from the running app / Xcode console. S2 and S4 read
`/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md`.

Never commit `tokens.md` — it is captured data.

---

## Identifiers (already fixed — for reference)

- App bundle ID:                `com.polymathic.commutealert.s3probe`
- Widget extension bundle ID:   `com.polymathic.commutealert.s3probe.widget`
- Live Activity APNs topic:     `com.polymathic.commutealert.s3probe.push-type.liveactivity`
- Alert / background topic:     `com.polymathic.commutealert.s3probe`
- Team:                         `MSQSPT8P3W`
- App Group:                    `group.com.polymathic.commutealert.s3probe`

## Tokens

```
LIVE ACTIVITY push-to-start token:
<paste — long lowercase hex, appears ~1-5s after app launch, needs iOS 17.2+>

LIVE ACTIVITY per-activity push token:
<paste — appears after tapping "① Start locally"; valid only while that activity lives>

APNs device token (alert / background):
<paste — long lowercase hex, appears ~1-5s after app launch>
```

Captured at: <date/time>
Captured by: <name>

## Device

- iPhone model:        <e.g. iPhone 15 Pro>
- iOS version:         <e.g. 18.1>
- Paired Apple Watch:  <yes / no; if yes, watchOS version>

## Result checklist (report back)

- [ ] Automatic signing succeeded with NO manual developer-portal steps
      (if not, what needed manual work: ______________________________)
- [ ] Live Activity appeared on the Lock Screen from the LOCAL start (no push)
- [ ] All three tokens above captured
- [ ] Notification permission granted (Authorization row = authorized)
- [ ] "Activities enabled" row read `yes`

Notes / anything surprising:
<...>
