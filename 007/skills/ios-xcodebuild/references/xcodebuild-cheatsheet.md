# xcodebuild CLI Reference

## Build

```bash
# Build for iOS Simulator (generic)
xcodebuild -scheme AppName \
    -destination 'generic/platform=iOS Simulator' \
    -configuration Debug \
    -derivedDataPath ./build/DerivedData \
    build

# Build for specific simulator
xcodebuild -scheme AppName \
    -destination 'platform=iOS Simulator,id=<UDID>' \
    -configuration Debug \
    build

# Build for device
xcodebuild -scheme AppName \
    -destination 'generic/platform=iOS' \
    -configuration Release \
    CODE_SIGN_IDENTITY="Apple Development" \
    DEVELOPMENT_TEAM="ABCDE12345" \
    build
```

## Platform Management

```bash
# Download iOS simulator SDK
xcodebuild -downloadPlatform iOS

# List available SDKs
xcodebuild -showsdks

# Show Xcode version
xcodebuild -version
```

## Simulator (xcrun simctl)

```bash
# List all devices
xcrun simctl list devices

# List available (bootable) devices
xcrun simctl list devices available

# List as JSON (for scripting)
xcrun simctl list devices available -j

# Create a new simulator
xcrun simctl create 'iPhone 17' \
    com.apple.CoreSimulator.SimDeviceType.iPhone-17 \
    com.apple.CoreSimulator.SimRuntime.iOS-26-5

# Boot / shutdown
xcrun simctl boot <UDID>
xcrun simctl shutdown <UDID>

# Install / uninstall app
xcrun simctl install <UDID> /path/to/App.app
xcrun simctl uninstall <UDID> com.bundle.id

# Launch / terminate
xcrun simctl launch <UDID> com.bundle.id
xcrun simctl terminate <UDID> com.bundle.id

# Stream logs
xcrun simctl spawn <UDID> log stream --predicate 'subsystem == "com.bundle.id"'

# Erase all data
xcrun simctl erase <UDID>

# Open Simulator.app
open -a Simulator
```

## Code Signing

```bash
# Ad-hoc sign (simulator only)
codesign --force --sign - App.app

# Sign with identity
codesign --force --sign "Apple Development" --entitlements entitlements.plist App.app

# Verify signature
codesign --verify --deep App.app
```

## Device (xcrun devicectl — Xcode 15+)

```bash
# List connected devices
xcrun devicectl list devices

# Install app on device
xcrun devicectl device install app --device <UDID> /path/to/App.app
```

## Useful Build Settings (passed to xcodebuild)

| Setting | Purpose |
|---------|---------|
| PRODUCT_BUNDLE_IDENTIFIER | Bundle ID |
| INFOPLIST_FILE | Path to Info.plist |
| SWIFT_VERSION | Swift language version |
| CODE_SIGN_IDENTITY | Signing identity |
| DEVELOPMENT_TEAM | Team ID for signing |
| GENERATE_INFOPLIST_FILE | YES to auto-generate |
| -derivedDataPath | Where build output goes |
| -skipPackagePluginValidation | Skip SPM plugin checks |
| -allowProvisioningUpdates | Auto-update profiles |
