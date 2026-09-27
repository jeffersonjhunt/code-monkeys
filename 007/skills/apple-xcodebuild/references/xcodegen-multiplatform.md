# XcodeGen for single- and multi-platform apps

`project.yml` is the source of truth; the `.xcodeproj` is generated and gitignored. `xc-build.py`
and `xc-test.py` regenerate it every run, so adding or removing files needs no extra step.

## One target, several platforms

```yaml
targets:
  App:
    type: application
    supportedDestinations: [iOS, macOS]     # one target → iPhone, iPad and a native Mac app
    sources: [Sources/App, Resources]
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.example.app
        GENERATE_INFOPLIST_FILE: YES
        TARGETED_DEVICE_FAMILY: "1,2"       # iPhone + iPad
        INFOPLIST_KEY_UILaunchScreen_Generation: YES
        INFOPLIST_KEY_UIApplicationSceneManifest_Generation: YES
        INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone: "UIInterfaceOrientationPortrait …"
        INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad: "… all four …"
```

- `supportedDestinations` replaces `platform:`. The Mac build is native SwiftUI/AppKit, not Mac
  Catalyst (Catalyst would be the `macCatalyst` destination).
- Settings apply to every destination; scope one with an SDK condition, e.g.
  `SOME_SETTING[sdk=macosx*]: …` or `[sdk=iphone*]`.
- In code, branch with `#if os(macOS)` / `#if os(iOS)`.
- The deployment target per platform goes in `options.deploymentTarget` (`iOS: "17.0"`,
  `macOS: "14.0"`).

## The TEST_HOST trap (multi-platform unit tests)

A hosted unit-test target gets `TEST_HOST = $(BUILT_PRODUCTS_DIR)/App.app/App` — the iOS bundle
layout — for **every** destination. On macOS the binary is `App.app/Contents/MacOS/App`, so
`xcodebuild test` fails before running anything:

```
xcodebuild: error: … Could not find test host for AppTests: TEST_HOST evaluates to ".../Debug/App.app/App"
```

The bootstrap template fixes it with SDK-conditional settings on the test target:

```yaml
  AppTests:
    type: bundle.unit-test
    supportedDestinations: [iOS, macOS]
    dependencies: [{ target: App }]
    settings:
      base:
        GENERATE_INFOPLIST_FILE: YES
        TEST_HOST[sdk=macosx*]: $(BUILT_PRODUCTS_DIR)/App.app/Contents/MacOS/App
        BUNDLE_LOADER[sdk=macosx*]: $(TEST_HOST)
```

## Schemes

Give the app target a `scheme:` with `testTargets:` so `xcodebuild -scheme App test` runs them.
Without one, there is no guarantee the scheme xcodebuild finds includes your tests (the
template always declares it).

## Local Swift packages

```yaml
packages:
  Engine:
    path: Packages/Engine
targets:
  App:
    dependencies:
      - package: Engine
```

Test the package on its own with `xc-test.py --package Packages/Engine` (and, if it has no Apple
framework imports, with `swift test` on Linux too).

## Pinning XcodeGen

`.xcodegen-version` holds one version (e.g. `2.45.4`). The skill builds each version once into
`~/Library/Caches/apple-xcodebuild/xcodegen/<version>/` on the Mac and reuses it. A project that
vendors its own XcodeGen (avatar: `tools/XcodeGen` submodule + Makefile) keeps working with its
own tooling; `xc-build.py` simply regenerates with the cached copy of the same version.
