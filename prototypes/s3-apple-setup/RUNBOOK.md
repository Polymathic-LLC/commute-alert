# S3 Runbook — get the Live Activity probe onto a physical iPhone

Work through this in **one sitting** (~30–45 min, most of it waiting on Xcode and
the device). Everything the agent could do is done: the Swift sources and the
Xcode project exist and compile. What is left needs a Mac with Xcode, your Apple
Developer account, and a physical iPhone in your hand.

At the end you will have:
- a Live Activity visible on the iPhone lock screen, started locally with **no
  push involved** (this is the S3 pass/fail bar), and
- three tokens pasted into `prototypes/s3-apple-setup/tokens.md` for S2 and S4.

---

## Part 0 — Have these ready

- [ ] **Paid Apple Developer Program** membership active on team **`MSQSPT8P3W`**,
      with your Apple ID on that team (role App Manager or Admin). A *free* Apple
      account cannot enable Push Notifications and this will not work.
- [ ] **Physical iPhone on iOS 17.2 or newer** (18+ preferred). Check Settings →
      General → About → iOS Version. Push-to-start Live Activities do not exist
      before 17.2.
- [ ] **USB cable** for the iPhone.
- [ ] **Xcode 26.2** (already installed on this Mac) signed in to that Apple ID:
      Xcode → Settings → Accounts → your Apple ID is listed and shows the team.
- [ ] Note your **iPhone model + exact iOS version**, and whether a **paired
      Apple Watch** exists — you will report these back.

---

## Part 1 — Open the project

The project is committed, so:

```
open prototypes/s3-apple-setup/S3Probe.xcodeproj
```

**Only if you change targets or add/remove source files later** you regenerate it:

```
brew install xcodegen        # once
cd prototypes/s3-apple-setup
xcodegen generate
```

`project.yml` is the source of truth; `S3Probe.xcodeproj` is a build artifact that
happens to be committed for convenience.

**If you started this runbook before and hit `CoreDeviceError 3000` on install:**
pull the fix first, then reopen:

```
git -C /Users/bradleybares/Git/commute-alert/.claude/worktrees/s3-apple-setup pull
```

(That commit adds the bundle-identifier keys the built `.app` was missing. In
Xcode: **Product → Clean Build Folder** (⇧⌘K) before rebuilding.)

---

## Part 2 — Signing (Xcode)

The project already carries `DEVELOPMENT_TEAM = MSQSPT8P3W` and automatic signing
(from `project.yml`), so this is mostly **confirmation** — but you still have to
let Xcode do the one-time App ID / App Group / profile registration, once per
target. The sources build clean from a cold cache on this exact Mac (Xcode 26.2),
so anything that goes red here is signing/provisioning, not code.

Do this for **both** targets.

1. In the Project navigator (left), click the blue **S3Probe** project icon at the
   top.
2. Under **TARGETS**, select **S3Probe**.
3. Open the **Signing & Capabilities** tab.
4. Confirm **Automatically manage signing** is ticked and **Team** already shows
   the team whose ID is `MSQSPT8P3W`. If Team shows "None" or an error, pick the
   right team from the dropdown.
5. Watch the status line under Team. Xcode registers the App ID, the App Group
   `group.com.polymathic.commutealert.s3probe`, and the Push Notifications
   capability, then creates a provisioning profile — 10–30 s. **If it goes red,
   copy the exact message** (it names the real cause) and check **Troubleshooting**
   or paste it to the agent.
6. Under **TARGETS**, now select **S3ProbeWidget** and repeat steps 3–5. It gets
   its own App ID (`...s3probe.widget`) and profile, and shares the App Group.

You should already see these capability tiles (they come from the checked-in
entitlements / Info.plist, you do **not** add them by hand):
- **Push Notifications** (S3Probe target)
- **App Groups** — with `group.com.polymathic.commutealert.s3probe` ticked (both targets)
- **Background Modes** — with **Remote notifications** ticked (S3Probe target)

If **App Groups** shows the group with a hollow/greyed checkbox, tick it, then
click the refresh arrow if one appears.

---

## Part 3 — Prepare the iPhone

1. Plug the iPhone into the Mac. Unlock it. Tap **Trust** on "Trust This
   Computer?" and enter the passcode.
2. First connection only: Xcode shows **"Preparing <device> for development"** in
   the Devices window — let it finish (can take a few minutes).
3. On the iPhone: **Settings → Privacy & Security → Developer Mode → On**. The
   phone restarts; after unlock, confirm **Turn On**. (If "Developer Mode" is not
   in that menu, it appears only after step 2 completes — reconnect and wait.)

---

## Part 4 — Build and run to the device

1. In the Xcode toolbar, click the run-destination dropdown (next to the scheme
   name **S3Probe**) and pick your iPhone under **iOS Device**, not a simulator.
2. Press **⌘R**.
3. First run: the iPhone may show **"Untrusted Developer"**. On the iPhone:
   **Settings → General → VPN & Device Management → [your Apple ID / dev cert] →
   Trust**, then press **⌘R** again.
4. The app launches to a screen titled **S3 Probe**.
5. Open the Xcode console: **View → Debug Area → Activate Console** (⌘⇧C / ⌘⇧Y).
   Every event is logged with an `[S3]` prefix — the tokens are printed there too.

> **Capture the APNs device token now, before anything else.** It appears in the
> **Tokens** section (and console) within ~5 s of this first launch, and it alone
> unblocks other work downstream. Copy it straight into `tokens.md` (Part 7)
> immediately — don't wait for Parts 5–7. The push-to-start token usually lands in
> the same few seconds; grab that too if it's there.

---

## Part 5 — Grant permissions on the device

1. In the app, **Notifications** section → tap **Request permission** → **Allow**
   on the system prompt. The "Authorization" row should change to `authorized`.
2. Confirm Live Activities are allowed: **Settings → S3 Probe → Live Activities**
   → toggle **On** (it defaults on). Back in the app, the **Activities enabled**
   row should read `yes`. If it reads `no`, the local-start step will refuse.

---

## Part 6 — The S3 pass/fail check: start a Live Activity locally

1. In the app, **Live Activity** section → tap **① Start locally (no push)**.
2. **Lock the iPhone** (side button). Within a second or two a Live Activity card
   should appear on the **Lock Screen** reading *"Local start — no push involved"*
   with "CR-Worcester · Boston Landing" above it.
   - On a Dynamic Island device it also shows there when unlocked.
   - A brief banner may appear first.
3. Wake the phone, return to the app, tap **② Local update**. The card's headline
   changes to *"Local update at HH:MM:SS"* and the status flips to `delayed`.
4. Tap **③ End**. The card ends (it may linger briefly in an "ended" state — Apple
   keeps ended activities up to 4 h; that is expected).

**If the card appears from step 1, S3's core question is answered: ActivityKit
works on real hardware independent of APNs.** If it does not appear, see
**Troubleshooting** and still finish Part 7 for whatever tokens did arrive.

---

## Part 7 — Capture the three tokens

The app shows a **Tokens** section with three rows. Each has a **Copy** button
once iOS has issued it. They also print to the Xcode console (`[S3] ... token =`).

| Row in the app | When it appears | Used by |
|---|---|---|
| **LIVE ACTIVITY push-to-start token** | ~1–5 s after launch (needs iOS 17.2+) | S2 push-to-start, S4 |
| **LIVE ACTIVITY per-activity push token** | after you tap **① Start locally** | S2 update/end, S4 |
| **APNs device token (alert / background)** | ~1–5 s after launch | S2 alert + background push, S4 |

Then — paste into the **main checkout**, not this worktree (S2 and S4 read from
there, and this worktree may be torn down):

```
cp /Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.example.md \
   /Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md
```

Open `/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md`
and paste each token on its line, plus the device info and the short result
checklist at the bottom. `tokens.md` is captured data — never commit it (add
`prototypes/s3-apple-setup/tokens.md` to the repo-root `.gitignore` if it isn't
covered). S2 and S4 read this file; they will not ask again.

> The **per-activity** push token is only valid while that activity is alive and
> can rotate. For S2/S4, start a fresh activity (**① Start locally**) right before
> the push test and copy the token again if needed. The **push-to-start** and
> **device** tokens are stable across relaunches (they can still rotate; just
> re-copy if the app logs a new one).

---

## Part 8 — Report back

Fill the checklist at the bottom of `tokens.md`:

- [ ] Automatic signing succeeded with **no manual developer-portal steps** — or,
      if not, exactly which capability/registration required manual work.
- [ ] Live Activity appeared on the **Lock Screen** from the local start (Part 6).
- [ ] All **three tokens** captured.
- [ ] iPhone model + exact iOS version.
- [ ] Paired Apple Watch: yes / no.

That closes S3 and unblocks S4.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Signing error: *"Failed to register bundle identifier"* or *"...cannot be registered to your development team"* | The App ID `com.polymathic.commutealert.s3probe` may already exist under another team, or your Apple ID lacks portal rights. Fix rights, **or** change the prefix: in `project.yml` set a new `PRODUCT_BUNDLE_IDENTIFIER` for both targets + `options.bundleIdPrefix`, update the two `.entitlements` App Group strings to match, `xcodegen generate`, and tell the orchestrator the new IDs (S2's Live Activity topic must match). |
| *"Provisioning profile doesn't include the aps-environment entitlement"* | Push Notifications not yet on the App ID. Usually fixed by toggling **Automatically manage signing** off/on, or pressing **Try Again**. Otherwise enable **Push Notifications** on the App ID at developer.apple.com → Certificates, IDs & Profiles. |
| App Groups checkbox stays hollow / *"Couldn't create App Group"* | Same portal-rights issue. Automatic signing normally creates `group.com.polymathic.commutealert.s3probe` for you; if it can't, create it manually on the portal and tick it on both targets. |
| Widget target won't sign | You skipped Part 2 step 7. Select **S3ProbeWidget**, Signing & Capabilities, same team, automatic. |
| **Activities enabled** row says `no` | Settings → S3 Probe → Live Activities → On. Also check a Focus mode isn't suppressing them. |
| Live Activity never appears despite `yes` | Lock the screen to look (it is a Lock Screen surface). Check Settings → Face ID & Passcode → **Live Activities** (allow when locked). Check Notification settings for the app aren't set to "Off". |
| **push-to-start token** row stays `— not issued yet —` | Device is below iOS 17.2 (the log says `push-to-start UNAVAILABLE`), or relaunch the app once. push-to-start requires 17.2+. |
| No **APNs device token** | Device offline at launch, or a Console error `APNs device-token registration FAILED: ...` — read the reason in the console and relaunch. |
| *"Preparing device"* never finishes / device not offered as a destination | Unlock the phone, unplug/replug, `Window → Devices and Simulators` → check for a message. A reboot of the iPhone usually clears it. |
| Build fails only for the device, fine for simulator | Almost always signing. Re-check Part 2 for **both** targets and that **Team** is set, not "None". |
