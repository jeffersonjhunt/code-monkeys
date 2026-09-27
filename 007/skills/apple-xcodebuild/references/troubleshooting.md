# Troubleshooting

Symptom → cause → fix. Each row happened in a real session.

| Symptom | Cause | Fix |
|---|---|---|
| `Host key verification failed` | Mac not in `known_hosts` (checking stays on) | `ssh-keyscan -H host.docker.internal >> ~/.ssh/known_hosts` |
| `xcrun simctl …` prints `Install Started … Install Failed: Authorization is required` | Xcode's first-launch packages (CoreSimulator, MobileDevice…) missing or older than this Xcode; `-checkFirstLaunchStatus` exits 69 | on the Mac: `sudo xcodebuild -runFirstLaunch` |
| `== Runtimes ==` empty, no simulators | simulator runtime not downloaded | on the Mac: `xcodebuild -downloadPlatform iOS` (creates default devices) |
| `Could not find test host for …Tests: TEST_HOST evaluates to ".../App.app/App"` on macOS | multi-platform test target uses the iOS bundle layout | SDK-conditional `TEST_HOST` — see xcodegen-multiplatform.md |
| `errSecInternalComponent` / `Command CodeSign failed` | identity's key unusable over SSH | `--adhoc` — see signing-and-tcc.md |
| `xcodebuild: WARNING: Using the first of multiple matching destinations … arm64 … x86_64` | Apple silicon Mac offers both archs for `platform=macOS` | harmless; arm64 is chosen |
| xc-shot `--platform macos` exits 2 | SSH cannot see GUI-session windows | take it on the Mac, or UI tests |
| `fatal: detected dubious ownership in repository` right after a Mac build | Docker Desktop file sharing briefly reports new/changed dirs as root-owned | transient — retry; do not add `safe.directory` for it |
| The iPhone SE is not in the device list | the iOS 27 runtime created no SE simulator by default | pick the smallest current phone (`--device "iPhone 17e"`) or check `xcrun simctl list devicetypes` and `simctl create` one |
| A build "succeeds" but nothing changed / an old app launches | using a tool that searches for "some .app" | `xc-run` launches exactly what `build/xc/build-<platform>.json` recorded |
| First build takes a minute before compiling | XcodeGen being built into the Mac's cache | once per XcodeGen version |
