# Changelog — apple-xcodebuild

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
  at launch; `xc-shot` takes simulator screenshots.
- Test suite drives every script through a fake `ssh` that runs the remote script locally
  against fake Apple tools, so the Mac-side logic is tested without a Mac.
- Review round 1 (all found before release): XcodeGen pinned to verified commits, not mutable
  tags; `xc-run` no longer reports a running iOS app as crashed (`grep -q` under pipefail
  SIGPIPE'd `launchctl` — reproduced on a real simulator); app paths are regex-escaped for
  `pgrep`/`pkill`; a remote exit 255 is no longer mistaken for an ssh failure; `xc-test` gained
  `--adhoc`/`--setting`; logs and result bundles are pruned to the newest 10; `xc-shot
  --appearance` restores the previous appearance.
