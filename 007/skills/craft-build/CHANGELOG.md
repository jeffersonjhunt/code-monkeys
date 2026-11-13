# Changelog

## 1.0.0

- Initial release. Refresh a suite of macOS app workspaces into `.dmg` artifacts on a build Mac,
  driven over ssh from a primate.
- `scripts/craft-all.sh`: generalized from the loose, unversioned script that lived on the build
  host — now takes `--root`/`$CRAFT_ROOT` (so the one versioned copy runs against any workspace),
  `--manifest`/`$CRAFT_MANIFEST` (clone any listed repo not yet present, so adding an app is one
  manifest line, across orgs), a `--list` dry run, and a robust PATH for non-login ssh on macOS.
  Discovery, `--ff-only` pulls, per-app drift, packaging and the report are unchanged.
- Config (`BUILD_HOST`, `CRAFT_ROOT`, `CRAFT_ARCH`, …) is read from env or
  `~/.config/craft-build.conf`; the public repo hardcodes no host, path or repo URL.
