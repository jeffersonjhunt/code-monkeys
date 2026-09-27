# Changelog — ios-xcodebuild

## [1.1.0] - 2026-09-27

- **Deprecated** in favour of `apple-xcodebuild`. No fixes: the skill still reports a failed
  build as success (`xcodebuild … | tail -5` over SSH). It will be removed once
  `apple-xcodebuild` has replaced it.
