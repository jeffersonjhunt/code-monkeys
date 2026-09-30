# Changelog — apple-xcodebuild

## [1.2.1] - 2026-09-30

- A failed read of the Mac's desktop session is reported as that ("could not read …"), no longer
  as "nobody is logged in"; `xc-test` still refuses macOS tests when it cannot tell.
- On a Mac, `HOST_IP` sends the scripts to another Mac just as `XC_HOST` does — the same two
  settings the SSH target is read from.

## [1.2.0] - 2026-09-30

- The scripts run on the Mac itself: on macOS (unless `XC_HOST` names another Mac) every command
  runs locally and paths need no mapping, so a project cloned only on a build Mac is driven with
  `ssh mac 'python3 …/xc-build.py --project-dir /Users/…/app'`. `XC_LOCAL=1`/`0` forces the choice.
  `xc-doctor` reports a `host` check instead of `ssh` there. SKILL.md › Projects that live on the Mac.
- macOS UI tests survive a sleeping display: `xc-test` wakes it first and holds it on
  (`caffeinate -d`) for the run — the session reads as locked while the display sleeps, even with
  the screen lock off, and every UI test failed "Running Background". A password-locked screen or
  no desktop login is refused up front with the fix, not after 60 s per test (`--allow-locked`
  for schemes without UI tests). `xc-doctor` has a `screen-lock` check.
  Waking is not always enough (an external display turned off again despite `caffeinate`), so a
  build Mac should also never turn its display off; SKILL.md › macOS UI tests.

## [1.1.1] - 2026-09-27

- Docs: macOS UI tests fail "Failed to activate application … Running Background" while someone
  is using the Mac; rerun with it idle (SKILL.md › macOS UI tests, troubleshooting).

## [1.1.0] - 2026-09-27

- `xc-test --packages-only --package DIR` works without an Xcode project (logs in the package's
  `.build/xc/logs`), so an engine package can be tested before the app exists.
- `xc-doctor` checks Automation Mode for macOS UI tests (a warning with the one-time fix).
- SKILL.md gains "macOS UI tests (XCUITest)": click not tap on macOS 27, setup in the launch
  environment, `-ApplePersistenceIgnoreState YES`, Automation Mode without a prompt. The
  references record that no Accessibility grant is needed, where it lives on macOS 27, the SSH vs
  GUI-session note, and that git's ownership glitch after Mac runs can last 10+ seconds.

## [1.0.1] - 2026-09-27

- `xc-doctor` reports an invalid or unpinned `.xcodegen-version` as a failed `xcodegen` check
  (with its fix) and still runs every other check; it used to stop at that one error.

## [1.0.0] - 2026-09-27

- New skill, superseding `ios-xcodebuild`: one skill for iOS, iPadOS and macOS, including
  cross-platform apps with a single multiplatform target.
- XcodeGen projects (`project.yml`), with XcodeGen built once per pinned version into a cache on
  the Mac — no Homebrew, no per-project submodule.
- Remote commands run as `bash -s` scripts under `set -euo pipefail`; xcodebuild's real exit
  status is reported. (`ios-xcodebuild` piped the build into `tail`, so failures read as success.)
- `xc-doctor` checks everything that blocked real sessions: first-launch components, simulator
  runtimes, path visibility, and whether codesigning works over SSH.
- `xc-test` fails on zero tests; `xc-run` launches the exact recorded build and fails on a crash
  at launch; `xc-shot` takes simulator screenshots and — with the Screen Recording grant for
  `sshd-keygen-wrapper` — macOS screenshots of the app's own window only (a small Swift helper,
  compiled once on the Mac, finds the window; `xc-doctor` checks the grant).
- Test suite drives every script through a fake `ssh` that runs the remote script locally
  against fake Apple tools, so the Mac-side logic is tested without a Mac.
- Review round 1 (all found before release): XcodeGen pinned to verified commits, not mutable
  tags; `xc-run` no longer reports a running iOS app as crashed (`grep -q` under pipefail
  SIGPIPE'd `launchctl` — reproduced on a real simulator); app paths are regex-escaped for
  `pgrep`/`pkill`; a remote exit 255 is no longer mistaken for an ssh failure; `xc-test` gained
  `--adhoc`/`--setting`; logs and result bundles are pruned to the newest 10; `xc-shot
  --appearance` restores the previous appearance.
