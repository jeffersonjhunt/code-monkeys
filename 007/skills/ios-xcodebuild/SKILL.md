---
name: ios-xcodebuild
description: Bootstrap, build, and deploy iOS apps from a Docker container via SSH to a macOS host using xcodebuild. Use when creating a new iOS project, building for simulator/device, deploying to simulator, or troubleshooting Xcode CLI builds.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# ios-xcodebuild

Build and deploy iOS apps entirely from CLI tools inside a Docker container. Compilation and simulator control happen on the macOS host via SSH. No Xcode IDE is ever opened.

## Architecture

```
Container (Linux)          SSH →          macOS Host
├── Edit source code                      ├── xcodebuild (compile)
├── Run build/deploy scripts              ├── codesign (sign)
└── AI agents / tools                     ├── xcrun simctl (simulator)
                                          └── iOS Simulator.app
```

The project directory is bind-mounted so the host sees file changes immediately.

## When to Use

- Bootstrapping a new iOS app project from scratch
- Building an iOS app for simulator or device
- Deploying and running on an iOS simulator
- Troubleshooting xcodebuild errors, missing SDKs, or simulator issues
- Any iOS development task where Xcode GUI is not available

## Prerequisites

- macOS host with Xcode CLI tools (`xcode-select --install`)
- iOS Simulator SDK installed (`xcodebuild -downloadPlatform iOS`)
- SSH access from container to host (key-based, no password)
- Project directory bind-mounted between container and host

## Usage

### Bootstrap a new project

```bash
./scripts/ios-bootstrap.sh MyApp com.example.myapp
```

Creates the full project structure: `Package.swift`, SwiftUI entry point, `Info.plist`, build/run scripts.

### Build

```bash
# Set environment
export HOST_USER=<mac-user>
export HOST_IP=host.docker.internal
export HOST_PROJECT_PATH="/Users/<mac-user>/path/to/project"

# Build for simulator
./scripts/ios-build.sh simulator debug

# Build for device (requires TEAM_ID)
TEAM_ID=ABCDE12345 ./scripts/ios-build.sh device release
```

### Deploy to simulator

```bash
./scripts/ios-run.sh simulator
```

### Direct xcodebuild (via SSH)

```bash
ssh $HOST_USER@$HOST_IP "cd '$HOST_PROJECT_PATH' && xcodebuild \
    -scheme MyApp \
    -destination 'generic/platform=iOS Simulator' \
    -configuration Debug \
    -derivedDataPath ./build/DerivedData \
    build"
```

## Project Structure

A minimal SPM-based iOS project:

```
MyApp/
├── Package.swift              # executableTarget (not library!)
├── Sources/MyApp/
│   ├── MyAppApp.swift         # @main SwiftUI entry
│   └── ContentView.swift
├── Resources/Info.plist       # iOS bundle metadata
├── scripts/
│   ├── ios-build.sh           # Compile via SSH → xcodebuild
│   └── ios-run.sh             # Deploy via SSH → xcrun simctl
└── build/                     # (gitignored) DerivedData output
```

## Key Concepts

### SPM executableTarget → .app Bundle

Swift Package Manager with `.executableTarget` produces a bare binary, NOT a `.app` bundle. The build script must:

1. Compile with `xcodebuild`
2. Create `Avatel.app/` directory
3. Copy binary into it
4. Copy and process `Info.plist` (substitute `$(PRODUCT_BUNDLE_IDENTIFIER)`, `$(PRODUCT_NAME)`)
5. `codesign --force --sign -` the bundle

### Simulator Deployment (xcrun simctl)

```bash
xcrun simctl list devices available | grep iPhone   # Find a simulator
xcrun simctl boot <UDID>                            # Boot it
xcrun simctl install <UDID> /path/to/App.app        # Install
xcrun simctl launch <UDID> com.bundle.id            # Launch
open -a Simulator                                    # Show window
```

### Installing the iOS SDK

Xcode 15+ requires separate platform downloads:

```bash
xcodebuild -downloadPlatform iOS    # ~8.5 GB download
```

## Gotchas

| Issue | Cause | Fix |
|-------|-------|-----|
| "Unable to find destination" | iOS SDK not installed | `xcodebuild -downloadPlatform iOS` |
| "Invalid Resource 'Resources'" | Wrong `resources:` path in Package.swift | Remove or fix the path relative to target |
| Build succeeds but no .app | SPM executables don't produce bundles | Wrap binary manually (see above) |
| "Scheme not found" | Stale SPM workspace | Delete `.swiftpm/` on host |
| Slow first build | Package resolution + module precompilation | Subsequent builds are incremental |
| Simulator shows black screen | Wrong arch | Rebuild targeting the specific device UDID |

## Scripts

- `scripts/ios-bootstrap.sh` — Scaffold a new iOS project
- `scripts/ios-build.sh` — Build the project (wraps xcodebuild + .app packaging)
- `scripts/ios-run.sh` — Deploy and launch on simulator or device

## Dependencies

- macOS host with Xcode 15+ (CLI tools only)
- SSH client in the container
- Python 3 (for simulator auto-detection JSON parsing in run script)
