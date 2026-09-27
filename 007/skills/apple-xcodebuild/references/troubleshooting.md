# Troubleshooting

Symptom → cause → fix. Each row happened in a real session.

| Symptom | Cause | Fix |
|---|---|---|
| macOS UI test: every `tap()` logs "Synthesize event" for ~5 s and nothing happens | macOS 27 no longer delivers synthesized taps to controls | use `click()` on macOS (see SKILL.md › macOS UI tests) |
| macOS UI test: the app shows a menu bar but no window, so no element is found | unknown launch arguments are treated as files to open, and/or a saved "no windows" state is restored | pass setup in `launchEnvironment`; add `-ApplePersistenceIgnoreState YES` to `launchArguments` |
| macOS UI test run pops a Touch ID / Apple Watch prompt, or fails "Denied authentication" | Automation Mode needs authentication each time | once: `sudo automationmodetool enable-automationmode-without-authentication` |
| `xc-test --package` fails "no project.yml" on a package with no app yet | (fixed in 1.1) | `--packages-only --package DIR --project-dir DIR` |
| `Host key verification failed` | Mac not in `known_hosts` (checking stays on) | `ssh-keyscan -H host.docker.internal >> ~/.ssh/known_hosts` |
| `xcrun simctl …` prints `Install Started … Install Failed: Authorization is required` | Xcode's first-launch packages (CoreSimulator, MobileDevice…) missing or older than this Xcode; `-checkFirstLaunchStatus` exits 69 | on the Mac: `sudo xcodebuild -runFirstLaunch` |
| `== Runtimes ==` empty, no simulators | simulator runtime not downloaded | on the Mac: `xcodebuild -downloadPlatform iOS` (creates default devices) |
| `Could not find test host for …Tests: TEST_HOST evaluates to ".../App.app/App"` on macOS | multi-platform test target uses the iOS bundle layout | SDK-conditional `TEST_HOST` — see xcodegen-multiplatform.md |
| `errSecInternalComponent` / `Command CodeSign failed` | identity's key unusable over SSH | `--adhoc` — see signing-and-tcc.md |
| `xcodebuild: WARNING: Using the first of multiple matching destinations … arm64 … x86_64` | Apple silicon Mac offers both archs for `platform=macOS` | harmless; arm64 is chosen |
| xc-shot `--platform macos` exits 2; the window list is empty for the app's pid | SSH sessions lack the Screen Recording grant, so the window server hides other apps' windows (it is *not* a GUI-session problem, and needs no root) | grant **sshd-keygen-wrapper** under Privacy & Security ▸ Screen & System Audio Recording; `xc-doctor` reports it as `screen-recording` |
| `fatal: detected dubious ownership in repository` right after a Mac build or test run | Docker Desktop file sharing reports new/changed dirs as root-owned for a while — it can flap for 10+ s, failing some git commands in a sequence and not others | wait and check (`git status` a few times) before git after a Mac run; verify pushes landed (`git ls-remote`); do not add `safe.directory` for it |
| The iPhone SE is not in the device list | the iOS 27 runtime created no SE simulator by default | pick the smallest current phone (`--device "iPhone 17e"`) or check `xcrun simctl list devicetypes` and `simctl create` one |
| A build "succeeds" but nothing changed / an old app launches | using a tool that searches for "some .app" | `xc-run` launches exactly what `build/xc/build-<platform>.json` recorded |
| First build takes a minute before compiling | XcodeGen being built into the Mac's cache | once per XcodeGen version |
