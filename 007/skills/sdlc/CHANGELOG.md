# Changelog — sdlc

## [1.2.1] - 2026-08-07

- Description names the release phase; it had lagged the v1.2.0 phase split.

## [1.2.1] - 2026-08-07

- Version bump (patch)

## [1.2.0] - 2026-08-07

- Split land into land (push the branch) and release (merge, last). Deploy the branch sha and observe BEFORE merging; release.merge_by replaces land.merge_by, which stays as an alias.

## [1.2.0] - 2026-08-07

- Version bump (minor)

## [1.1.2] - 2026-08-07

- State file resolves at the repo root instead of cwd, so a lifecycle survives changing directory; status reports its path.

## [1.1.2] - 2026-08-07

- Version bump (patch)

## [1.1.1] - 2026-08-07

- Verify rules: a worktree omits gitignored files so config-gated tests silently skip there; prefer a fixture over ambient config.

## [1.1.1] - 2026-08-07

- Version bump (patch)

## [1.1.0] - 2026-08-07

- Add the 'undeployed' tier for substantive work that ships nothing (tests, dev tooling, specs) — keeps verify and review, drops deploy and observe.

## [1.1.0] - 2026-08-07

- Version bump (minor)

## [1.0] - 2026-08-07

- Initial release: nine-phase lifecycle, three tiers, gate scripts and CLAUDE.md overrides.
