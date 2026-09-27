# xcodebuild / simctl cheatsheet

The raw commands behind the scripts, for when you need something they do not do. Run them on the
Mac (`ssh <user>@host.docker.internal '…'`). Paths are Mac paths (`hostpath <dir>` maps them).

## Mac readiness

```bash
xcode-select -p                         # must be /Applications/Xcode.app/Contents/Developer
xcodebuild -version
xcodebuild -checkFirstLaunchStatus; echo $?   # 0 = ok; 69 = run: sudo xcodebuild -runFirstLaunch
xcodebuild -showsdks
xcodebuild -downloadPlatform iOS        # simulator runtime
xcrun simctl runtime list
```

## Build

```bash
# Scheme and supported platforms
xcodebuild -project App.xcodeproj -list
xcodebuild -project App.xcodeproj -scheme App -showBuildSettings -json | grep SUPPORTED_PLATFORMS

# iOS Simulator (any), macOS (this Mac), iOS device (needs a team)
xcodebuild -project App.xcodeproj -scheme App -configuration Debug \
    -destination 'generic/platform=iOS Simulator' -derivedDataPath build/DerivedData build
xcodebuild -project App.xcodeproj -scheme App -configuration Debug \
    -destination 'platform=macOS' -derivedDataPath build/DerivedData \
    CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY=- build
xcodebuild -project App.xcodeproj -scheme App -configuration Release \
    -destination 'generic/platform=iOS' CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM=ABCDE12345 \
    -allowProvisioningUpdates build

# Where the product is (TARGET_BUILD_DIR + FULL_PRODUCT_NAME, PRODUCT_BUNDLE_IDENTIFIER)
xcodebuild … -destination '…' -showBuildSettings -json
```

Never pipe `xcodebuild` into `tail`/`grep` over SSH without `set -o pipefail`: the pipeline's
status becomes the last command's, and a failed build reads as success. Redirect to a log file
and keep `$?`.

## Test

```bash
xcodebuild … -destination 'platform=macOS' -resultBundlePath build/r.xcresult test
xcodebuild … -destination 'platform=iOS Simulator,id=<UDID>' -resultBundlePath build/r.xcresult test
xcrun xcresulttool get test-results summary --path build/r.xcresult --compact
#   → totalTestCount, passedTests, failedTests, skippedTests, result
swift test --package-path Packages/Engine
```

## Simulator (xcrun simctl)

```bash
xcrun simctl list devices available -j
xcrun simctl boot <UDID>
xcrun simctl bootstatus <UDID> -b          # wait until boot has finished
xcrun simctl install <UDID> path/App.app
xcrun simctl launch <UDID> com.bundle.id   # prints "com.bundle.id: <pid>"
xcrun simctl terminate <UDID> com.bundle.id
xcrun simctl io <UDID> screenshot out.png
xcrun simctl ui <UDID> appearance dark
xcrun simctl status_bar <UDID> override --time 9:41
xcrun simctl spawn <UDID> log stream --predicate 'process == "App"'
xcrun simctl create 'Small Phone' com.apple.CoreSimulator.SimDeviceType.iPhone-17e \
    com.apple.CoreSimulator.SimRuntime.iOS-27-0
xcrun simctl erase <UDID>
open -a Simulator
```

## macOS app

```bash
open build/DerivedData/Build/Products/Debug/App.app      # LaunchServices, not the bare binary
pgrep -f 'App.app/Contents/MacOS/App'
log stream --style compact --predicate 'process == "App"'
pkill -f 'App.app/Contents/MacOS/App'
tccutil reset All com.bundle.id                          # forget permission grants
defaults delete com.bundle.id                            # forget preferences
```

## Signing

```bash
security find-identity -v -p codesigning
codesign --force --sign - App.app                        # ad-hoc
codesign -dvv App.app 2>&1 | grep -E 'Authority|TeamIdentifier|Signature'
codesign --verify --deep --strict App.app
```

## Devices (xcrun devicectl)

```bash
xcrun devicectl list devices
xcrun devicectl device install app --device <UDID> path/App.app
xcrun devicectl device process launch --device <UDID> com.bundle.id
```
