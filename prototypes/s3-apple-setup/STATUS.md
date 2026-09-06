STATUS: RUNNING
Last updated: 2026-09-06 (agent local, day 0 — human now attached, working RUNBOOK.md interactively)
Summary: Agent-side S3 work is complete and verified. The human is attached and working RUNBOOK.md step by step with the agent driving. Critical path for S2 (device token → failure catalogue), S4, and S5. Progress tracked in the checklist below; tokens will be reported to the orchestrator the moment each one appears.

## Runbook progress (live)

- [ ] Project opens in Xcode 26.2 from the worktree
- [ ] Automatic signing OK — S3Probe target (App ID + App Group + Push registered)
- [ ] Automatic signing OK — S3ProbeWidget target
- [ ] Developer Mode on + device trusted
- [ ] App builds & runs on the physical iPhone
- [ ] Notification permission granted; "Activities enabled" = yes
- [ ] **S3 pass/fail:** Live Activity appears on Lock Screen from local start (no push)
- [ ] Token captured: APNs device token  → unblocks S2 alert/background
- [ ] Token captured: Live Activity push-to-start token
- [ ] Token captured: Live Activity per-activity push token
- [ ] tokens.md filled in the MAIN checkout

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

**Handoff for S2/S4:** tokens land in the MAIN checkout at `/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md` (NOT the worktree — that may be torn down). That directory already contains `tokens.example.md` + `WHERE-IS-THE-PROJECT.md`; the human copies the example to `tokens.md` and fills it in. Live Activity APNs topic is `com.polymathic.commutealert.s3probe.push-type.liveactivity`.

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
