# Changelog — apple-xcodebuild

## [1.3.1] - 2026-10-01

- No button-pressing on the build Mac from a signer change: macOS 27 asks "“App” differs from
  previously opened versions" on the Mac's screen whenever an app is opened with a different
  signer, and test runners hang until someone answers. `xc-build` and `xc-test` now check how the
  macOS app already on the Mac is signed (codesign) and refuse a run that would change it — ad-hoc
  vs team, one team vs another — with `--allow-signer-change` to switch on purpose.
- `xc-doctor` `other-copies`: warns about copies of the app elsewhere on the Mac (a TestFlight or
  App Store install) signed differently from the project's builds — alternating with them prompts too.

## [1.3.0] - 2026-10-01

- Signing over SSH with a dedicated keychain: when the Mac has an `api.env` (the file project
  Makefiles read), identity- and team-signed `xc-build`/`xc-test` runs unlock its signing keychain
  in the same remote session as `xcodebuild`, sign with `--keychain`, and provision with its App
  Store Connect API key. The password stays on the Mac.
- `xc-doctor`'s `codesign` check signs its probe the same way, so "ok" means builds can sign. It
  used to try only the login keychain and report it locked while `make` signed fine; it now also
  says when the signing keychain won't unlock, or unlocks but its key isn't open to codesign.
- `xc-test` names a dialog waiting on the Mac: when a macOS test runner "hung before establishing
  connection" and a system dialog is in front (UserNotificationCenter and the like), it says so,
  with the fix. Seen on the first team-signed run: macOS 27 asks "“…-Runner” differs from
  previously opened versions" when a binary's signer changes, and the runner waits for the answer.
- signing-and-tcc.md › A signing keychain for SSH: the verified setup (keychain, CSR-made
  identity, key partition list, WWDR G3, API key, api.env). SKILL.md's configuration table had a
  blank line splitting it in two; fixed.

## [1.2.2] - 2026-10-01

- A screen saver is named as such. On macOS 27 it runs inside loginwindow, the session reads as
  locked while it shows, and `caffeinate -u` does not dismiss it; `xc-test` used to report "the
  Mac's screen stayed locked after waking the display" with the screen-lock fix. It now says a
  screen saver is showing, with the Lock Screen ▸ "Start Screen Saver when inactive" fix, and
  `xc-doctor` has a `screen-saver` check that warns while it can start.

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
