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
  - **Installability gate (added after F11):** `plutil -p` on the built
    `S3Probe.app/Info.plist` and the embedded `.appex/Info.plist` shows resolved
    `CFBundleIdentifier` / `CFBundleExecutable` / `CFBundlePackageType`.
- **Answer.** Yes. The agent can own the whole source + project side. XcodeGen is
  the mechanism that lets a project exist without the UI; the generated
  `S3Probe.xcodeproj` is committed so a human without XcodeGen just opens it.
- **Confidence.** High for "compiles, links, and produces an installable bundle".
  The parts that only a device can prove (signing succeeds, Live Activity actually
  renders, tokens actually issue) are F4 and are still open. **See F11** — an
  earlier version of this finding treated BUILD SUCCEEDED as sufficient and it was
  not.

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

## F11. `xcodebuild` success is not an installability check — and `GENERATE_INFOPLIST_FILE=NO` silently drops required bundle keys

- **What happened.** The project was first written with `GENERATE_INFOPLIST_FILE:
  "NO"` plus a hand-written `Info.plist` for each target. Those files listed
  `CFBundleDisplayName`, versions, `NSSupportsLiveActivities`, etc. but **not**
  `CFBundleIdentifier`, `CFBundleExecutable`, `CFBundlePackageType`, or
  `CFBundleName`. With `GENERATE_INFOPLIST_FILE=NO` nothing synthesizes those, so
  the built `S3Probe.app/Info.plist` (and the widget `.appex`) shipped with **no
  `CFBundleIdentifier`**. `xcodebuild ... build` returned **BUILD SUCCEEDED** for
  both the simulator and unsigned-device slices anyway. The failure only appeared
  when the human tried to install on a real device: **CoreDeviceError 3000**.
- **Why the earlier verification missed it.** "BUILD SUCCEEDED" was reported as
  evidence the product was ready. A build succeeding proves the sources compile
  and link; it says nothing about whether the resulting bundle is *installable*.
  Those are different checks and only the first was run.
- **Fix.** `GENERATE_INFOPLIST_FILE: "YES"` while keeping the explicit
  `INFOPLIST_FILE` for each target. Xcode then merges the synthesized bundle keys
  on top of the hand-written file; our file still contributes
  `NSSupportsLiveActivities`, `UIBackgroundModes`, and the widget's `NSExtension`
  dict. Verified in the built product:
  - `S3Probe.app/Info.plist`: `CFBundleIdentifier = com.polymathic.commutealert.s3probe`, `CFBundleExecutable = S3Probe`, `CFBundlePackageType = APPL`, `CFBundleName = S3Probe` — all resolved, no literal `$(…)`.
  - `S3ProbeWidget.appex/Info.plist`: `CFBundleIdentifier = …s3probe.widget`, `CFBundlePackageType = XPC!`, `NSExtensionPointIdentifier = com.apple.widgetkit-extension` preserved.
- **The installability gate now in the loop** (run on the built `.app` and the
  embedded `.appex` before telling anyone a build is ready):

  ```
  plutil -p <built .app>/Info.plist | grep -E "CFBundleIdentifier|CFBundleExecutable|CFBundlePackageType"
  plutil -p <built .app>/PlugIns/<ext>.appex/Info.plist | grep -E "CFBundleIdentifier|CFBundleExecutable|CFBundlePackageType"
  ```

  Values must be the resolved strings, not `$(PRODUCT_BUNDLE_IDENTIFIER)`.
- **Relevance to layer 2.** `ios/CLAUDE.md` says the production project is created
  through the Xcode UI, which always turns on `GENERATE_INFOPLIST_FILE` and would
  not have hit this. A *generated* project (XcodeGen / a hand-written pbxproj /
  SPM) can, and any CI that builds the real target must include the installability
  gate above, not just a compile.
- **Confidence.** High — root cause reproduced (missing key in the built plist)
  and the fix verified against the built product.

## F10. Toolchain specifics worth carrying forward (Xcode 26.2 / iOS 26 SDK)

Recorded because layer-2 iOS work and any CI config will hit the same environment.

- **Versions:** Xcode 26.2 (17C52), Swift 6.2 compiler, iOS 26.2 device + simulator
  SDKs. `RECOMMENDED_IPHONEOS_DEPLOYMENT_TARGET` is 15.0; this prototype pins
  **17.2** (Live Activity push-to-start floor) and builds fine.
- **XcodeGen 2.46.0** emits a project Xcode 26.2 opens with no migration prompt
  (`objectVersion` 77, `PBXFileSystemSynchronizedRootGroup` folder groups). Scheme
  is generated shared under `xcshareddata/`.
- **`SWIFT_VERSION = 5.0` is load-bearing here.** With the Swift 6.2 toolchain the
  default would be Swift 6 language mode, which turns Sendable / actor-isolation
  warnings into errors. One real case surfaced: a `UIApplicationDelegate` method
  receiving `[AnyHashable: Any]` `userInfo`. Fix that also holds under Swift 6
  mode: annotate the whole `AppDelegate` `@MainActor` so the non-Sendable payload
  never crosses an actor boundary (the callbacks are main-thread anyway). The real
  `ios/` target should decide Swift 6 vs 5 mode deliberately — this prototype
  chose 5 to stay a throwaway.
- **Cold-cache reproducibility:** `rm -rf ~/Library/Developer/Xcode/DerivedData/S3Probe-* && xcodebuild ... clean build`
  → **BUILD SUCCEEDED**, zero warnings. So a build failure the human sees in the
  runbook is environment/signing, not the sources.
- **Unsigned device-slice build works** (`-sdk iphoneos CODE_SIGNING_ALLOWED=NO
  CODE_SIGNING_REQUIRED=NO`) — handy for a compile gate in CI without a signing
  identity.
- **Confidence.** High — all verified on this machine.

## F9. The throwaway content-state is deliberately not the production contract

`CommuteActivityAttributes.ContentState` here carries `v`, `displayStatus`,
`headline`, `minutesToDeparture?`, `updatedAt`. This is only rich enough for S4 to
exercise updates / collapse-id / the 8-hour cap. `docs/display-contract.md` leaves
the real field set "Open" pending S6 (trip selection) and S4 (budget); nothing in
this prototype should be read as resolving it.
