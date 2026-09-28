---
name: apple-xcodebuild
description: Scaffold, build, test, run and screenshot iOS, iPadOS and macOS apps from a Linux container by driving xcodebuild on a macOS host over SSH. Handles single-platform and cross-platform (one multiplatform target) XcodeGen projects. Use for any Apple-platform app work where the Xcode IDE is not available — new projects, CI-style builds, running on a simulator or the Mac, or diagnosing why the Mac cannot build.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.1.1"
---

# apple-xcodebuild

Build Apple-platform apps without opening Xcode. You edit in the container; compiling, signing,
simulators and launching happen on the Mac over SSH. The project folder is shared, so the Mac sees
every edit immediately and build logs land back in the project.

```
Container (Linux)                SSH (bash -s)               macOS host
├── edit sources                 ───────────────▶           ├── xcodegen (cached)
├── xc-*.py (this skill)                                     ├── xcodebuild build / test
└── read build/logs, build/xc    ◀─── shared folder ───▶    ├── xcrun simctl · open
                                                             └── Simulator.app · the app
```

Replaces `ios-xcodebuild` (removed 2026-09-27: iOS only, and it reported failed builds as successes).

## Quick start

```bash
X=~/.claude/skills/apple-xcodebuild/scripts

python3 $X/xc-doctor.py --no-project          # is the Mac ready? (run this first, always)
python3 $X/xc-bootstrap.py Demo --bundle-id com.example.demo    # iOS + macOS by default
cd Demo
python3 $X/xc-build.py                        # every platform the scheme supports
python3 $X/xc-test.py                         # scheme tests on each platform
python3 $X/xc-run.py --platform ios-sim       # or --platform macos
python3 $X/xc-shot.py                         # screenshot → build/shots/ (or --platform macos)
python3 $X/xc-run.py --platform ios-sim --stop
```

Every script prints **JSON on stdout** (`"ok": true|false`) and progress on stderr, and exits
**0** ok · **1** build/test/user failure · **2** environment problem (Mac unreachable, no path
mapping, unsupported). All take `--help` and `--project-dir` (default: `.`, searched upward).

## Scripts

| Script | Does |
|---|---|
| `xc-doctor.py` | Checks SSH, `xcode-select`, first-launch components, SDKs, simulators, that the project is visible on the Mac, the XcodeGen cache, the Screen Recording grant macOS screenshots need, Automation Mode for macOS UI tests, and — for macOS projects that sign with an identity — that codesigning actually works over SSH. Every non-ok check carries a `fix`. |
| `xc-bootstrap.py <App>` | Scaffolds an XcodeGen project: one app target for `--platforms ios,macos` (either or both), Swift 6, generated Info.plist, asset catalog, Swift Testing target, `.gitignore`, pinned `.xcodegen-version`. Scaffolds into an existing dir (e.g. a fresh repo) only if nothing would be overwritten; extends an existing `.gitignore`. |
| `xc-build.py` | Regenerates the project from `project.yml`, builds `--platform ios-sim\|ios-device\|macos\|all` in `--config debug\|release`. Full log in `build/logs/`; the built app's path and bundle id (from the build settings) in `build/xc/build-<platform>.json`. `--setting KEY=VALUE` passes extra build settings; `--adhoc` forces ad-hoc macOS signing. |
| `xc-test.py` | `xcodebuild test` per platform (a concrete simulator for iOS) with counts read from the `.xcresult`; `--package DIR` runs `swift test` for a local package — with `--packages-only` no Xcode project is needed (logs go to the package's `.build/xc/logs`). **Zero tests is a failure**, and so is a run whose counts cannot be read. Takes the same `--setting` and `--adhoc` as `xc-build`. |
| `xc-run.py --platform ios-sim\|macos` | Launches the *recorded* app. Simulator: boot, wait for boot, install, launch. Mac: `open` (LaunchServices). Re-checks the process after `--settle` s so a crash-on-launch fails. `--logs N` captures N s of the app's log; `--stop` terminates it. |
| `xc-shot.py` | iOS: the booted simulator's screen (status bar pinned to 9:41; `--appearance dark` for the shot, then restored). macOS: **only the app's own window**, never the rest of the desktop — needs the Screen Recording grant below. |

## Configuration

| Setting | Source (first wins) |
|---|---|
| Mac address | `XC_HOST`, `HOST_IP`, default `host.docker.internal` |
| Mac user | `XC_HOST_USER`, `HOST_USER`, else the user in `HOST_WORKSPACE` (`/Users/<user>/…`) |
| Container → Mac paths | `HOST_PROJECT_PATH` + `HOST_PROJECT_ROOT`, else the container's `hostpath` helper |
| XcodeGen version | project's `.xcodegen-version` (`2.45.4`, or `<version>@<commit>` for versions the skill does not know), default 2.45.4 — always verified against a pinned commit |
| macOS signing | `--adhoc`; else `.signid` (named identity, manual); else team (`--team`, `TEAM_ID`, `.devteam`); else ad-hoc |
| Device signing | team required (`--team`, `TEAM_ID`, `.devteam`) |

The project must live in a host-shared directory (e.g. `~/workspace`) — `xc-doctor` checks it.

## One-time Mac setup

```bash
ssh-keyscan -H host.docker.internal >> ~/.ssh/known_hosts   # in the container; host key checks stay ON
# on the Mac (needs your password):
sudo xcodebuild -runFirstLaunch          # system components matching this Xcode
xcodebuild -downloadPlatform iOS         # simulator runtime (~8 GB), creates default simulators
```

For macOS screenshots only: System Settings ▸ Privacy & Security ▸ Screen & System Audio Recording ▸
enable **sshd-keygen-wrapper** (`/usr/libexec/sshd-keygen-wrapper`, the SSH server; add it with +).
Without it the window server hides other apps' windows from SSH sessions. Note this lets *any* SSH
session to your account record the screen.

XcodeGen needs no setup: the first build clones the pinned version, checks the clone is at the
pinned commit (a moved tag is refused, never built), and compiles it into
`~/Library/Caches/apple-xcodebuild/xcodegen/<version>-<commit>/` on the Mac (~1 min), shared by
all projects.

## macOS UI tests (XCUITest)

UI tests run on both platforms through `xc-test.py`, but macOS 27 needs four things (each cost a real
debugging session):

1. **Click, don't tap.** On macOS 27 `XCUIElement.tap()` no longer reaches controls ("Synthesize
   event" takes ~5 s and nothing happens). Use `click()` on macOS, `tap()` elsewhere — a small
   `press()` / `drag(to:)` extension with `#if os(macOS)` keeps tests cross-platform.
2. **Pass test setup in `launchEnvironment`, not `launchArguments`.** macOS treats unknown
   command-line arguments as files to open, and an app launched to "open a file" skips its first
   window — the test then finds a menu bar and no UI.
3. **Launch with `-ApplePersistenceIgnoreState YES`.** A run that quit with no window open saves
   "no windows", and XCUITest's launch (unlike Finder or the Dock) doesn't send the event that
   would open one anyway.
4. **Automation Mode without a prompt.** Once, on the Mac:
   `sudo automationmodetool enable-automationmode-without-authentication` — otherwise every run
   asks for Touch ID / an Apple Watch and fails unattended. `xc-doctor` checks it.
5. **Nobody using the Mac during the run.** While someone is working on the Mac, macOS 27 won't
   let the test runner pull the app to the front: a test waits 60 s and fails "Failed to activate
   application … (current state: Running Background)", often only the first few of a run. Rerun
   with the Mac idle before suspecting the code.

No Accessibility (Device Control & Data Access) grant is needed for any of this.

## Limits

- **Identity signing over SSH** — the login keychain's private keys are usually unusable from SSH
  (`errSecInternalComponent`). `xc-doctor` detects it; build with `--adhoc`.
- **Physical devices** — `--platform ios-device` builds; installing/launching on hardware is not
  automated.
- **Timeouts** stop the local `ssh` only; a remote `xcodebuild` keeps running until it finishes.
- Logs (`build/logs/`) and result bundles (`build/xc/results/`) keep the newest 10 of each kind.

## References

- `references/xcodebuild-cheatsheet.md` — raw commands for everything the scripts do
- `references/xcodegen-multiplatform.md` — the `project.yml` shape, and the TEST_HOST trap
- `references/signing-and-tcc.md` — signing precedence, the SSH keychain problem, TCC grants
- `references/troubleshooting.md` — symptom → cause → fix, from real sessions
