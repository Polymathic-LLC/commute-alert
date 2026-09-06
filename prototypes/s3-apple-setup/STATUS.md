STATUS: BLOCKED
Last updated: 2026-09-06 (agent local, day 0)
Summary: Agent-side S3 work is complete and verified — Swift sources + a generated Xcode project for the throwaway Live Activity probe both build clean against the iOS 26.2 SDK (simulator and device slices). Everything remaining requires a human with Xcode + an Apple Developer account + a physical iPhone. The single end-to-end runbook is RUNBOOK.md. No independent work remains, so status is BLOCKED rather than RUNNING.

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

**Handoff for S2/S4:** tokens land in `prototypes/s3-apple-setup/tokens.md`. Live Activity APNs topic is `com.polymathic.commutealert.s3probe.push-type.liveactivity`.

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
