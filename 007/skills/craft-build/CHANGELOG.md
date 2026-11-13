# Changelog

## 1.1.0

- Add a **publish/deploy step**. When `CRAFT_DEPLOY_DEST` (or `--deploy-dest`) is set, each
  successfully-built app's `.dmg` + matching `-cli-*.zip` are rsync'd there over ssh from the build
  host after packaging (old versions kept, never deleted). Deploys by default when a destination is
  configured; `--deploy` forces it, `--no-deploy` skips. Uses macOS-`openrsync`-safe flags (`-rtz`,
  no `--chmod`). The report and `--list` now show the deploy destination and per-app deploy status.
- This restores a step that used to be a manual copy through an SMB mount at `/Volumes/Software` and
  silently lapsed when that share migrated to NFS+Kerberos — now it is scripted and mount-independent.

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
