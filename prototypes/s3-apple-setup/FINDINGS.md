# S3 — Apple project setup: findings

Findings are recorded as they are established. "Confidence" is the agent's own,
and separates what was verified on this machine from what still depends on a human
with a physical device.

---

## F1. A throwaway app + widget extension + one Live Activity builds clean on this toolchain

- **Question.** Can the S3 deliverable (minimal app, widget extension, one Live
  Activity) be assembled and made to compile without driving the Xcode UI?
- **Evidence.**
  - Toolchain on this Mac: Xcode 26.2 (17C52), Swift 6.2, iOS 26.2 SDK, iOS 26.2
    simulator runtimes present. No physical device attached.
  - Project is generated from `project.yml` by XcodeGen 2.46.0 (`xcodegen generate`).
  - `xcodebuild -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build` → **BUILD SUCCEEDED**.
  - `xcodebuild -sdk iphoneos -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build` → **BUILD SUCCEEDED** (compiles for the device slice; signing deferred to the human).
  - Widget extension is embedded at `S3Probe.app/PlugIns/S3ProbeWidget.appex`; `ValidateEmbeddedBinary` passed.
  - No warnings, no errors.
- **Answer.** Yes. The agent can own the whole source + project side. XcodeGen is
  the mechanism that lets a project exist without the UI; the generated
  `S3Probe.xcodeproj` is committed so a human without XcodeGen just opens it.
- **Confidence.** High for "compiles and links". The parts that only a device can
  prove (signing succeeds, Live Activity actually renders, tokens actually issue)
  are F4 and are still open.

## F2. The `ios/CLAUDE.md` "must be created via Xcode UI" constraint is about the *production* project, and is worked around here, not violated

- **Question.** How to satisfy S3 given the stated constraint?
- **Evidence / reasoning.** `ios/CLAUDE.md` requires the real `CommuteAlert`
  project to be created through Xcode so targets/entitlements are configured
  correctly. DERISKING S3 explicitly says to build the prototype as a *separate
  throwaway project* under `prototypes/s3-apple-setup/` and "keep `ios/` clean".
  This prototype does exactly that: `ios/` is untouched; the throwaway uses
  distinct bundle IDs (`...s3probe*`) so its App IDs / profiles never collide
  with the real ones.
- **Answer.** The constraint is respected. Nothing here informs how the real
  project is created — S3's job is only to get a Live Activity onto a device and
  capture tokens.
- **Confidence.** High.

## F3. `ios/CommuteAlert.xcodeproj` is still staged-but-broken — not S3's to fix, flagged for the orchestrator

- **Question.** DERISKING S3 notes the staged `ios/CommuteAlert.xcodeproj`
  references sources deleted in `cd07ced`. Resolve before building on it.
- **Evidence.** `git show :ios/CommuteAlert.xcodeproj/project.pbxproj` references
  `PBXFileSystemSynchronizedRootGroup`s `CommuteAlert/`, `CommuteAlertTests/`,
  `CommuteAlertUITests/` — none of which exist on disk. Commit `cd07ced`
  ("chore: remove ios scaffold in favor of multiplatform setup") deleted them but
  left the `.xcodeproj` staged as re-added.
- **Answer / action.** S3 does not touch `ios/`. The prototype sidesteps it
  entirely. Recommendation for whoever owns `ios/`: `git rm -r --cached
  ios/CommuteAlert.xcodeproj` and recreate the real project fresh through Xcode
  per `ios/CLAUDE.md` when layer-2 implementation starts. Recorded here so it is
  not silently assumed handled.
- **Confidence.** High on the diagnosis; the fix is out of S3 scope.

## F4. OPEN — everything that needs the physical device

Cannot be answered on this machine. Folded into `RUNBOOK.md` for the human, and
into the day-0 batched ask via the orchestrator. Specifically unproven until the
runbook is worked:

- Automatic signing creates the App IDs + provisioning profiles for the app, the
  widget, the App Group `group.com.polymathic.commutealert.s3probe`, and the Push
  Notifications capability, on team `MSQSPT8P3W`, without manual portal work.
- The app installs and launches on the device.
- `Activity.request(...)` succeeds and a Live Activity appears on the lock screen
  with **no push involved** — the S3 "done" bar.
- The Live Activity **push-to-start** token is issued (needs iOS 17.2+) and the
  **per-activity** push token is issued after a local start.
- The standard **APNs device token** is issued (for S2/S4 alert + background push).

## F5. Bundle identifiers and the derived APNs topics (for S2 / S4)

Fixed, not placeholders:

| Thing | Value |
|---|---|
| App bundle ID | `com.polymathic.commutealert.s3probe` |
| Widget extension bundle ID | `com.polymathic.commutealert.s3probe.widget` |
| Live Activity APNs topic | `com.polymathic.commutealert.s3probe.push-type.liveactivity` |
| Alert / background APNs topic | `com.polymathic.commutealert.s3probe` |
| Apple team | `MSQSPT8P3W` |
| App Group | `group.com.polymathic.commutealert.s3probe` |
| Deployment target | iOS 17.2 |

## F7. `tokens.md` was NOT covered by the repo-root `.gitignore` — an assumed rule that did not exist

- **What happened.** The handoff plan called `tokens.md` "gitignored". The
  repo-root `.gitignore` had `prototypes/**/.secrets/` and `prototypes/**/data/`
  but **no pattern matching `tokens.md`**. The prototype-local
  `prototypes/s3-apple-setup/.gitignore` this session added covers the file only
  inside this branch's tree — it does nothing for the main checkout until merged.
- **Fix (done by the orchestrator).** Added `prototypes/**/tokens.md` to the
  repo-root `.gitignore`, verified with `git check-ignore`.
- **Lesson.** An assumed-but-absent ignore rule is exactly how a push token leaks
  later. When a workflow depends on a path being ignored, verify with
  `git check-ignore <path>` rather than assuming a glob covers it.
- **Confidence.** High — verified.

## F8. The human works the runbook from this worktree in place

- The orchestrator decided against a second worktree or a merge-to-main. The
  human opens `…/.claude/worktrees/s3-apple-setup/prototypes/s3-apple-setup/S3Probe.xcodeproj`
  directly — it is a normal on-disk working tree and git-locked, so it is not
  pruned. Tokens still get pasted into the **main-checkout** path
  (`/Users/bradleybares/Git/commute-alert/prototypes/s3-apple-setup/tokens.md`)
  so S2/S4 read them independent of the worktree.

## F9. The throwaway content-state is deliberately not the production contract

`CommuteActivityAttributes.ContentState` here carries `v`, `displayStatus`,
`headline`, `minutesToDeparture?`, `updatedAt`. This is only rich enough for S4 to
exercise updates / collapse-id / the 8-hour cap. `docs/display-contract.md` leaves
the real field set "Open" pending S6 (trip selection) and S4 (budget); nothing in
this prototype should be read as resolving it.
