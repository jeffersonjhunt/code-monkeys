---
name: craft-build
description: Refresh the Craft macOS app builds — pull, cargo-build, package a .dmg for each app in the suite on the build Mac, and publish the artifacts to a fileserver. Use when asked to "refresh the craft builds", "rebuild the craft/mac apps", "update the open-source app builds", "deploy/publish the craft apps", or to add a new app repo to the set. Builds run on the configured build host over ssh, NOT inside a primate. Host, workspace root, repo manifest and deploy destination come from env or ~/.config/craft-build.conf (never hardcoded here).
license: Apache-2.0
metadata:
  author: ooe
  version: "1.1.0"
---

# craft-build

Pull, build and package the suite of macOS app workspaces (the "Craft" apps and any peers) into
`.dmg` artifacts. **The build runs on a specific build Mac, reached over ssh — not inside a primate**
(macOS packaging, the cargo toolchain and the signing tools only exist there). An agent working from a
Linux primate drives it remotely.

This skill hardcodes **no** hostnames, usernames, paths or repo URLs — the public repo carries none.
The real values live in `~/.config/craft-build.conf` (or env), private to each machine; see
`craft-build.conf.example`. The per-repo list lives in a private manifest on the build host.

## When to use

- "refresh the craft builds", "rebuild the mac apps", "update the open-source app builds", "repackage
  the dmgs" — pull every app repo and repackage.
- "add <repo> to the builds" — add it to the manifest; the next refresh clones and builds it.
- You just want the current `.dmg` of one app (`--only <app>`).

## The shape of it (no private data)

- Each app is a Rust workspace repo cloned under one **ROOT** dir on the build Mac. The deliverable is
  a signed `.dmg` (plus a `-cli-*.zip`) in each app's `dist/release/`, which is then **published** to a
  fileserver (an rsync-over-ssh destination) so others can download it. "Build and deploy the same way"
  means: package and publish it like the others.
- Apps are discovered, not listed: `craft-all.sh` builds every sibling dir under ROOT that has
  `packaging/macos/package.sh`, reading its version from `[workspace.package]` in `Cargo.toml`. So an
  app that follows that convention needs **no** script change — only to be present under ROOT.
- A private **manifest** (`name = git-remote` lines) records every repo so a fresh Mac can re-clone the
  whole set, and so "add an app" is one line. The manifest may span orgs (the apps are not all the same
  author); that is fine — the build does not care who owns a repo.

## Configuration

The scripts read, in order: environment variables, then `${CRAFT_BUILD_CONF:-~/.config/craft-build.conf}`
if present. Nothing is baked into the repo. Copy `craft-build.conf.example` to
`~/.config/craft-build.conf` and fill it in (that file is private — never commit it):

```
BUILD_HOST=<the Mac where the app repos live and packaging runs>
BUILD_USER=<ssh user on that host>            # optional; else your ssh default
CRAFT_ROOT=<absolute path to the workspace root holding the app repos, on the build host>
CRAFT_ARCH=aarch64                            # aarch64 | x86_64 | universal
CRAFT_MANIFEST=<path to the manifest on the build host, default $CRAFT_ROOT/craft.manifest>
CRAFT_DEPLOY_DEST=<rsync-over-ssh publish target, user@host:/path; blank = build-only>
```

The **manifest** itself lives on the build host (co-located with the repos), e.g.
`$CRAFT_ROOT/craft.manifest`:

```
# name          = git remote
designcraft     = git@github.com:<org>/designcraft.git
solidcraft      = git@github.com:<other-org>/solidcraft.git
```

## How to run it

1. **Load config.** Read `~/.config/craft-build.conf` (or env). You need `BUILD_HOST` and `CRAFT_ROOT`
   at minimum. Build the ssh target as `${BUILD_USER:+$BUILD_USER@}$BUILD_HOST`.

2. **Sync the script to the host.** The versioned copy is this skill's `scripts/craft-all.sh`. Push it
   so the host always runs the current one (this also replaces any older loose copy):
   ```
   scp scripts/craft-all.sh "$TARGET:$CRAFT_ROOT/craft-all.sh"
   ```

3. **Dry-run first** to show the plan (what would clone, what would build) — no network, no build:
   ```
   ssh "$TARGET" "bash '$CRAFT_ROOT/craft-all.sh' --root '$CRAFT_ROOT' --list"
   ```

4. **Run it.** Packaging all apps takes many minutes, so launch it **detached** and poll — do not hold
   the ssh connection open for the whole build:
   ```
   ssh "$TARGET" "cd '$CRAFT_ROOT' && nohup bash craft-all.sh --root '$CRAFT_ROOT' --arch '${CRAFT_ARCH:-aarch64}' > craft-all.console.log 2>&1 & echo pid=\$!"
   ```
   Then poll `pgrep -f craft-all.sh` on the host until it is gone (a background waiter is ideal), and
   report `$CRAFT_ROOT/craft-all.report.txt` — per-app version, commit drift, build rc, the `.dmg`, and
   the deploy status. When `CRAFT_DEPLOY_DEST` is set, each rc=0 app is **published there automatically**
   (`.dmg` + `-cli-*.zip`, rsync-over-ssh from the build host, old versions kept); pass `--no-deploy` to
   build without publishing, or `--deploy-dest` to override. One app (`--only <app>`), skip pulling
   (`--no-pull`) or skip packaging (`--no-package`) as needed.

## Hard rules (where agents get stuck — don't)

1. **Builds are host-side.** Never try to `cargo`/package inside a primate — the toolchain and signing
   are only on the build Mac. Reach it over ssh and run there.
2. **Non-login ssh drops PATH** on macOS, so brew tools and shims come back "command not found".
   `craft-all.sh` sets a robust PATH itself (`/opt/homebrew/bin:/usr/local/bin:~/.local/bin:~/.cargo/bin`
   + system); keep that if you edit it.
3. **`--ff-only` pulls only.** The script never merges or resets — an app with real local commits that
   can't fast-forward is reported `PULL-FAILED` and still built at its current HEAD, never force-updated.
   Untracked junk (`.DS_Store`) does not block a fast-forward.
4. **Adding an app = a manifest line, not a code change.** As long as the repo has
   `packaging/macos/package.sh` and a `[workspace.package]` version, discovery handles the rest.
5. **Publish is rsync-over-ssh, not a mount.** The deploy writes to `CRAFT_DEPLOY_DEST` directly over
   ssh from the build host (which must have ssh access to it), as the ssh user. Don't reintroduce an
   NFS/SMB mount for this — a mount silently breaks on an auth/path change and the publish stops
   happening unnoticed (which is exactly how it lapsed before). The build host uses macOS `openrsync`,
   so the deploy uses only portable flags (`-rtz`, no `--chmod`); set the destination dir setgid if you
   want a consistent group.

## Tests

`007/skills/tests/test_craft_build.py` covers the pure logic (manifest parse → clone plan, discovery,
the `--list` dry run) against a fixture tree, with no network and no real build.
