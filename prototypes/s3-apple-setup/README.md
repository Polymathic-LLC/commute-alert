# prototypes/s3-apple-setup

Throwaway Live Activity probe app for DERISKING workstream **S3**. Not production
code; `ios/` is deliberately untouched.

**Goal:** get one Live Activity onto a physical iPhone and capture the two Live
Activity push tokens (+ the plain APNs device token) for S2 and S4.

## Layout

| Path | What |
|---|---|
| `project.yml` | XcodeGen spec — source of truth for the project |
| `S3Probe.xcodeproj` | Generated, committed so you can open without XcodeGen |
| `Sources/App/` | The app: token registration, local Live Activity control, a debug UI |
| `Sources/Widget/` | Widget extension: the `ActivityConfiguration` + a trivial static widget |
| `Sources/Shared/` | `CommuteActivityAttributes` — compiled into both targets |
| `RUNBOOK.md` | **Start here if you are the human.** End-to-end: signing → device → tokens |
| `FINDINGS.md` | What S3 established, and what is still open pending the device |
| `STATUS.md` | Orchestrator status channel |
| `tokens.example.md` | Template; copy to `tokens.md` (gitignored) and fill in |

## Regenerate the project

```
brew install xcodegen
cd prototypes/s3-apple-setup
xcodegen generate
```

## Verified on this Mac (no device)

Xcode 26.2, iOS 26.2 SDK. Both slices build clean:

```
xcodebuild -project S3Probe.xcodeproj -scheme S3Probe \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO build            # BUILD SUCCEEDED

xcodebuild -project S3Probe.xcodeproj -scheme S3Probe \
  -sdk iphoneos -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build   # BUILD SUCCEEDED
```

Installability gate (a build succeeding does not prove the bundle installs — see
`FINDINGS.md` F11). On the built product:

```
APP=~/Library/Developer/Xcode/DerivedData/S3Probe-*/Build/Products/Debug-iphonesimulator/S3Probe.app
plutil -p $APP/Info.plist | grep -E 'CFBundleIdentifier|CFBundleExecutable|CFBundlePackageType'
plutil -p $APP/PlugIns/S3ProbeWidget.appex/Info.plist | grep -E 'CFBundleIdentifier|CFBundleExecutable|CFBundlePackageType'
# values must be resolved strings, not $(PRODUCT_BUNDLE_IDENTIFIER)
```

Bundle IDs / topics are in `FINDINGS.md` §F5.
