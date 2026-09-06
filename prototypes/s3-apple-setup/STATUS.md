STATUS: RUNNING
Last updated: 2026-09-06 ~16:45 EDT (agent local) — human working RUNBOOK.md; 2 of 3 tokens captured
Summary: The app is running on the physical iPhone (both the push-to-start token and the APNs device token have been issued and are in tokens.md — S2 has used both and got 200s from APNs). Still open: the per-activity push token, the local-start Live Activity render check, and the Device section of tokens.md. An orchestrator report says S2 sent a push-to-start at 16:40 EDT and APNs returned 200 — waiting on the human to look at the phone and confirm whether an activity actually appeared and whether a per-activity token printed.

## Runbook progress (live)

- [x] Project opens in Xcode 26.2 from the worktree
- [x] App builds & runs on the physical iPhone (device tokens issued ⇒ signing + install + launch all worked; CoreDeviceError 3000 resolved by the GENERATE_INFOPLIST_FILE fix, commit 8cc68b7)
- [~] Automatic signing — S3Probe target: OK (app installed). S3ProbeWidget target: not separately confirmed.
- [x] Developer Mode on + device trusted (implied by a successful device install)
- [ ] Notification permission granted; "Activities enabled" = yes — NOT confirmed
- [ ] **S3 pass/fail:** Live Activity appears on Lock Screen from LOCAL start (no push) — NOT done (per-activity token still a placeholder)
- [x] Token captured: APNs device token — `b8f4c129…` in tokens.md → S2 unblocked
- [x] Token captured: Live Activity push-to-start token — `80dd43f6…` in tokens.md → S2 got a 200
- [ ] Token captured: Live Activity per-activity push token — STILL the template placeholder; PERISHABLE (valid only while its activity lives)
- [~] Device section of tokens.md: model = iPhone 15 Pro (iPhone16,1), iOS = 26.5 (both from tooling). Paired Apple Watch = STILL UNKNOWN (needs human; S4 batching it).
- [ ] Result checklist at the bottom of tokens.md filled

## tokens.md location

Left at the WORKTREE path `…/.claude/worktrees/s3-apple-setup/prototypes/s3-apple-setup/tokens.md` (the human created it there at 16:39, not the main checkout). S2 auto-discovered it and its reader is bound to that path — per the orchestrator, do NOT move it now; moving mid-flight breaks S2's reader.

## What a human needs to do — one sitting, ~30–45 min

**Full step-by-step: `prototypes/s3-apple-setup/RUNBOOK.md`.** In brief:

1. `open prototypes/s3-apple-setup/S3Probe.xcodeproj`.
2. Signing & Capabilities → Automatically manage signing → Team `MSQSPT8P3W`, for **both** targets (S3Probe and S3ProbeWidget). Let automatic signing register the App IDs, the App Group, and Push Notifications.
3. Enable Developer Mode on the iPhone; trust the Mac.
4. ⌘R to the physical device (not a simulator). Trust the developer cert on the phone if prompted.
5. In the app: tap **Request permission** → Allow. Confirm Settings → S3 Probe → Live Activities is On.
6. **S3 pass/fail:** tap **① Start locally (no push)**, lock the phone, confirm a Live Activity card appears on the Lock Screen. Tap ② then ③ to see update/end.
7. Copy the three tokens (Copy buttons in the app, or the Xcode console `[S3]` lines) into `prototypes/s3-apple-setup/tokens.md` (`cp tokens.example.md tokens.md` first — it is gitignored). Fill the result checklist at the bottom.

## Needs from human

**URGENT / time-sensitive (asked ~16:45 EDT, awaiting answer):** S2 sent a push-to-start at 16:40:14 EDT, APNs returned 200. If it rendered, an activity is now live on the phone with its own perishable per-activity token. Human, please check the phone + Xcode console and report:
1. Is there a Live Activity on the lock screen that nobody started by hand? What does it say?
2. Did an alert banner ("Commute monitoring started" / "Worcester Line delay") appear?
3. Does the console show a new per-activity push token printed around 16:40?
   → If yes to (3): paste it into the `LIVE ACTIVITY per-activity push token` line of tokens.md immediately — it dies with the activity.

**Device facts:** model = iPhone 15 Pro, iOS = 26.5 (both from Mac tooling, in tokens.md). **Paired Apple Watch: still need a yes/no from the human** — S4 is batching this into its ask. The Part 6 local-start render check and the per-activity token are now S4's to capture via its instrumentation.

**Confirmations for the day-0 batch:**
1. Paid Apple Developer Program membership active on team `MSQSPT8P3W`, your Apple ID on that team (App Manager or Admin). Free account will not work.
2. Physical iPhone on iOS 17.2+ (18+ preferred) — report model + exact iOS version.
3. Developer Mode enabled on that iPhone (Settings → Privacy & Security → Developer Mode), then reboot.
4. iPhone USB cable; tap "Trust This Computer" on first connect.
5. Xcode 26.2 signed into that Apple ID (already installed on this Mac).
6. Paired Apple Watch — yes/no. Only affects one S4 question; nothing blocks on it.

**Then work `RUNBOOK.md` end to end** and report back via the checklist in `tokens.md`:
- Did automatic signing succeed with NO manual developer-portal steps?
- Did the Live Activity appear on the Lock Screen from the local (no-push) start?
- Were all three tokens captured?
- iPhone model + iOS version; Apple Watch paired y/n.

**Handoff for S2/S4:** tokens are in `tokens.md` at the WORKTREE path (`…/.claude/worktrees/s3-apple-setup/prototypes/s3-apple-setup/tokens.md`). S2's reader is bound to that path — it stays there. Live Activity APNs topic is `com.polymathic.commutealert.s3probe.push-type.liveactivity`. (The earlier plan to keep it in the main checkout is superseded; see "tokens.md location" above.)

**Open logistics (orchestrator):** the Xcode project + sources + RUNBOOK.md + FINDINGS.md are only on branch `worktree-s3-apple-setup` (pushed to origin), not in the main checkout. Before the human can work RUNBOOK.md, that branch content needs to reach a normal working tree — either `git worktree add ../commute-alert-s3 worktree-s3-apple-setup`, or the orchestrator merges/cherry-picks it. Noted in `WHERE-IS-THE-PROJECT.md` in the main checkout.

**Note for the orchestrator (not S3's to fix):** `ios/CommuteAlert.xcodeproj` is still staged-but-broken — it references source folders deleted in `cd07ced`. S3 sidesteps `ios/` entirely. Recommend `git rm -r --cached ios/CommuteAlert.xcodeproj` and recreating the real project via Xcode per `ios/CLAUDE.md` when layer-2 work starts. Detail in FINDINGS.md §F3.

- **attach to approve `brew install xcodegen`** — already ran and succeeded this session; noted per protocol only in case a re-run prompts. XcodeGen 2.46.0 is on PATH.

## Activity log

- Read DERISKING.md S3, ios/CLAUDE.md, docs/push-flow.md, docs/display-contract.md.
- Toolchain: Xcode 26.2 (17C52), Swift 6.2, iOS 26.2 SDK, simulators present; no physical device on this host. Installed XcodeGen 2.46.0.
- Entered worktree `worktree-s3-apple-setup`. Created `prototypes/s3-apple-setup/`. `ios/` untouched.
- Wrote: shared `CommuteActivityAttributes`; app (`S3ProbeApp`, `AppDelegate`, `ProbeModel`, `LiveActivityController`, `ContentView`, Info.plist, entitlements); widget (`S3ProbeWidgetBundle`, `CommuteLiveActivity`, `CommuteStaticWidget`, Info.plist, entitlements); `project.yml`.
- `xcodegen generate` → `S3Probe.xcodeproj` (committed).
- `xcodebuild` simulator slice → BUILD SUCCEEDED. Device slice (unsigned) → BUILD SUCCEEDED. Widget extension embeds + ValidateEmbeddedBinary passes. Zero warnings.
- Wrote RUNBOOK.md, FINDINGS.md, tokens.example.md, README.md, .gitignore. Relayed bundle ID + prereqs to derisk-orchestrator.
- Committed prototype. Status → BLOCKED pending human execution of RUNBOOK.md.
- Orchestrator review: re-verified team ID `MSQSPT8P3W` + topic format `<bundle-id>.push-type.liveactivity` against the main checkout (`ios/CLAUDE.md`, `docs/push-flow.md`) — both intact, no conclusion rested on a missing file. Redirected the token drop-off to the main checkout: created `/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/{tokens.example.md,WHERE-IS-THE-PROJECT.md}`; updated RUNBOOK.md Part 7 + tokens.example.md to the absolute path.
- Orchestrator resolved logistics: human opens the project from this worktree in place (git-locked, not pruned); no second worktree, no merge to main. Orchestrator also fixed the real gap that `tokens.md` was not matched by the repo-root `.gitignore` (added `prototypes/**/tokens.md`, verified with `git check-ignore`). Recorded as FINDINGS.md §F7–F8.
- Human on a planned break until ~13:30 EDT; holding. Used the gap to: verify a cold-cache clean build (BUILD SUCCEEDED, and fixed the one Swift-6-mode Sendable warning in AppDelegate by making the class `@MainActor`); tighten RUNBOOK Part 2 (signing is pre-wired, so it's confirm-not-configure) and add an "capture the device token first, report it immediately" callout after Part 4; record toolchain specifics as FINDINGS.md §F10. No tokens captured yet (human hadn't started).
- **Device install failed for the human: CoreDeviceError 3000.** Root cause (S2 diagnosed, orchestrator + this session confirmed): `GENERATE_INFOPLIST_FILE` was `NO` with hand-written Info.plist files missing `CFBundleIdentifier` / `CFBundleExecutable` / `CFBundlePackageType` / `CFBundleName`, so the built `.app` had no bundle identifier and the device refused it. `xcodebuild` still said BUILD SUCCEEDED — a compile is not an installability check. Fixed: `GENERATE_INFOPLIST_FILE: YES` + keep explicit `INFOPLIST_FILE`; regenerated; verified with `plutil -p` on the built `.app` and `.appex` that `CFBundleIdentifier` etc. resolve. Committed `8cc68b7`/`f144117`, pushed. FINDINGS.md §F11. Added a `plutil` installability gate to the verification loop.
- **~16:39 EDT: the fix worked — app is running on the physical iPhone.** Human created `tokens.md` in the worktree and filled two of three: push-to-start token `80dd43f6…` and APNs device token `b8f4c129…`. S2 read both and got 200s from APNs (incl. a push-to-start send at 16:40:14). Per-activity token still unfilled; Device section still unfilled.
- **Corrected stale STATUS.md** (orchestrator flagged it: every box was unticked despite two tokens demonstrably captured). Checklist now reflects real state. Relayed the orchestrator's urgent "look at the phone now" questions to the human (activity rendered? banner? per-activity token in console ~16:40?). Awaiting the human's on-device observation — nobody has yet confirmed anything actually appeared on the device; a 200 from APNs is "accepted", not "rendered".
- Not sending any more pushes and not asking S2 to (orchestrator: every push drains the Live Activity update budget S4 must measure).
- **Device facts pulled from tooling** and written into tokens.md: **iPhone 15 Pro (iPhone16,1)**, **iOS 26.5** (device newer than the 26.2 SDK — fine; current-OS push-to-start semantics). Paired Apple Watch still UNKNOWN (not visible to Mac-side tooling — a watch pairs to the phone).
- **S4 (s4-live-activity) has taken over the device and the worktree.** It is instrumenting the probe app IN PLACE: adds `Sources/Shared/S4Log.swift` (App-Group NDJSON), a render-logging hook in `CommuteLiveActivity`, `Activity.activityUpdates` observation to capture push-started activities' per-activity tokens (the gap this session's `observe()` left), a collector panel, and ATS local-networking + `UIFileSharingEnabled` in Info.plist. I confirmed stand-down from worktree edits and handed over project gotchas (GENERATE_INFOPLIST_FILE trap, Shared→both-targets, Swift 5 mode, @MainActor AppDelegate, unverified widget signing, App-Group container check, two-process split). S3's remaining loose ends (per-activity token, render confirmation, Watch answer) are now folded into S4's harness and human ask.
