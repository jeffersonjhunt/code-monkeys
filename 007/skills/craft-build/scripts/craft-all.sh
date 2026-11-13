#!/usr/bin/env bash
# craft-all.sh — pull, build, package and publish a set of macOS app workspaces.
#
# Pure mechanism, no private data: it operates on whatever repos live under a ROOT
# directory. For every sibling directory that has packaging/macos/package.sh it:
#   0. (optional) clones any repo named in a manifest that is not yet present
#   1. git fetch + git pull --ff-only      (unless --no-pull)
#   2. records the drift since the previous HEAD
#   3. runs packaging/macos/package.sh --arch <arch>   (unless --no-package)
#   4. reports the resulting .dmg
#   5. (optional) deploys the .dmg + matching -cli .zip to DEPLOY_DEST via rsync-over-ssh
#
# Usage: craft-all.sh [--root DIR] [--manifest FILE] [--arch aarch64|x86_64|universal]
#                     [--no-pull] [--no-package] [--only "app1 app2 ..."]
#                     [--deploy | --no-deploy] [--deploy-dest USER@HOST:PATH] [--list]
#
#   --root DIR       workspace root holding the app repos (default: this script's dir,
#                    or $CRAFT_ROOT). Lets the one versioned copy run against any root.
#   --manifest FILE  "name = git-remote" lines; any name not already cloned under ROOT
#                    is cloned before the build (default: $CRAFT_MANIFEST, else
#                    $ROOT/craft.manifest if it exists). '#' comments and blanks ignored.
#   --deploy-dest X  rsync destination for built artifacts (default: $CRAFT_DEPLOY_DEST),
#                    e.g. user@host:/path. When set, each rc=0 app's .dmg and its
#                    matching -cli-*.zip are rsync'd there after packaging.
#   --deploy         force the deploy on (errors if no destination is configured).
#   --no-deploy      skip the deploy even if a destination is configured.
#                    Default: deploy iff a destination is configured.
#   --list           print the clone/build/deploy plan, then exit (no network, no build).
#
# Artifacts land in each app's dist/release/; old version-stamped builds are kept, both
# locally and at the destination (the deploy never deletes).
set -u

# Non-login ssh on macOS drops almost all PATH; package.sh needs brew tools, the cargo
# toolchain and ~/.local/bin shims. Set a robust PATH so this runs the same over ssh.
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CRAFT_ROOT:-$SELF_DIR}"
MANIFEST="${CRAFT_MANIFEST:-}"
ARCH="${CRAFT_ARCH:-aarch64}"
DEPLOY_DEST="${CRAFT_DEPLOY_DEST:-}"
DEPLOY=""          # "" = auto (deploy iff DEPLOY_DEST set); 1 = force on; 0 = skip
PULL=1
PACKAGE=1
ONLY=""
LIST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --arch) ARCH="$2"; shift 2 ;;
    --deploy-dest) DEPLOY_DEST="$2"; shift 2 ;;
    --deploy) DEPLOY=1; shift ;;
    --no-deploy) DEPLOY=0; shift ;;
    --no-pull) PULL=0; shift ;;
    --no-package) PACKAGE=0; shift ;;
    --only) ONLY="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help) awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$ROOT" 2>/dev/null && pwd)" || { echo "root not found: $ROOT" >&2; exit 1; }
[ -n "$MANIFEST" ] || { [ -f "$ROOT/craft.manifest" ] && MANIFEST="$ROOT/craft.manifest"; }

# resolve whether we deploy: explicit flag wins; otherwise deploy iff a destination is set
DO_DEPLOY=0
case "$DEPLOY" in
  1) [ -n "$DEPLOY_DEST" ] || { echo "--deploy needs a destination (CRAFT_DEPLOY_DEST / --deploy-dest)" >&2; exit 2; }; DO_DEPLOY=1 ;;
  0) DO_DEPLOY=0 ;;
  *) [ -n "$DEPLOY_DEST" ] && DO_DEPLOY=1 ;;
esac

ts() { date "+%Y-%m-%d %H:%M:%S"; }
REPORT="$ROOT/craft-all.report.txt"
say() { echo "$@" | tee -a "$REPORT"; }

workspace_version() {  # $1 = repo dir
  awk '/^\[/{p=($0=="[workspace.package]");next} p&&$1=="version"{gsub(/[" ]/,"",$3);print $3;exit}' "$1/Cargo.toml" 2>/dev/null
}

# resolve the clone plan from the manifest (name<TAB>remote for names missing under ROOT)
clone_plan() {
  [ -n "$MANIFEST" ] && [ -f "$MANIFEST" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    case "$line" in *=*) ;; *) continue ;; esac
    name="${line%%=*}"; name="$(echo "$name" | tr -d '[:space:]')"
    remote="${line#*=}"; remote="$(echo "$remote" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$name" ] && [ -n "$remote" ] || continue
    [ -d "$ROOT/$name/.git" ] && continue
    printf '%s\t%s\n' "$name" "$remote"
  done < "$MANIFEST"
}

if [ "$LIST" = 1 ]; then
  echo "root:     $ROOT"
  echo "manifest: ${MANIFEST:-<none>}"
  echo "arch:     $ARCH"
  echo "deploy:   $([ "$DO_DEPLOY" = 1 ] && echo "$DEPLOY_DEST" || echo "<off>")"
  echo "would clone:"
  clone_plan | while IFS=$'\t' read -r n r; do echo "  $n <- $r"; done
  echo "would build (dirs with packaging/macos/package.sh):"
  for d in "$ROOT"/*/; do
    [ -f "${d}packaging/macos/package.sh" ] || continue
    n="$(basename "$d")"
    if [ -n "$ONLY" ]; then case " $ONLY " in *" $n "*) ;; *) continue ;; esac; fi
    echo "  $n"
  done
  exit 0
fi

: > "$REPORT"
say "craft-all $(ts)  root=$ROOT arch=$ARCH pull=$PULL package=$PACKAGE deploy=$([ "$DO_DEPLOY" = 1 ] && echo "$DEPLOY_DEST" || echo off)"

# clone any manifest repos not yet present
clone_plan | while IFS=$'\t' read -r name remote; do
  say "cloning $name <- $remote"
  git -C "$ROOT" clone -q "$remote" "$name" >>"$ROOT/$name-pull.log" 2>&1 || say "  CLONE-FAILED $name (see $name-pull.log)"
done

# discover apps
apps=()
for d in "$ROOT"/*/; do
  [ -f "${d}packaging/macos/package.sh" ] || continue
  name="$(basename "$d")"
  if [ -n "$ONLY" ]; then case " $ONLY " in *" $name "*) ;; *) continue ;; esac; fi
  apps+=("$name")
done

say "apps: ${apps[*]:-<none found>}"
say ""

rows=()
for app in "${apps[@]}"; do
  dir="$ROOT/$app"
  cd "$dir" || continue
  br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  before="$(git rev-parse HEAD 2>/dev/null)"
  pullnote="skipped"
  if [ "$PULL" = 1 ]; then
    git fetch -q origin 2>>"$ROOT/$app-pull.log"
    if git pull -q --ff-only >>"$ROOT/$app-pull.log" 2>&1; then pullnote="ok"; else pullnote="PULL-FAILED"; fi
  fi
  after="$(git rev-parse HEAD 2>/dev/null)"
  if [ "$before" = "$after" ]; then
    drift="no change"
  else
    n="$(git rev-list --count "$before..$after" 2>/dev/null)"
    ss="$(git diff --shortstat "$before..$after" 2>/dev/null | sed 's/^ *//')"
    drift="$n commit(s); $ss"
  fi
  ver="$(workspace_version "$dir")"

  rc="-"; dmg="not-built"; dep="-"
  if [ "$PACKAGE" = 1 ]; then
    say "===== $app v$ver : package.sh --arch $ARCH  $(ts) ====="
    ( cd "$dir" && bash packaging/macos/package.sh --arch "$ARCH" ) >"$ROOT/$app-package.log" 2>&1
    rc=$?
    d="$(ls -t "$dir"/dist/release/*-"$ARCH".dmg 2>/dev/null | head -1)"
    [ -n "$d" ] && dmg="$(basename "$d")" || dmg="(none)"
    say "----- $app rc=$rc  dmg=$dmg  $(ts) -----"
    if [ "$DO_DEPLOY" = 1 ]; then
      if [ "$rc" = 0 ] && [ -n "$d" ]; then
        cli="$(ls -t "$dir"/dist/release/*-cli-*-"$ARCH".zip 2>/dev/null | head -1)"
        # openrsync-safe flags (macOS default rsync rejects --chmod): -rtz, no perm/owner preserve.
        if rsync -rtz "$d" ${cli:+"$cli"} "$DEPLOY_DEST/" >"$ROOT/$app-deploy.log" 2>&1; then
          dep="deployed"
        else
          dep="DEPLOY-FAILED"
        fi
        say "----- $app deploy=$dep -> $DEPLOY_DEST  $(ts) -----"
      else
        dep="skipped(rc=$rc)"
      fi
    fi
  fi
  rows+=("$app|$br|${before:0:9}|${after:0:9}|$pullnote|$ver|$rc|$dmg|$drift|$dep")
done

say ""
say "================ SUMMARY ================"
for r in "${rows[@]}"; do
  IFS='|' read -r app br before after pullnote ver rc dmg drift dep <<<"$r"
  say "$app ($br)  $before -> $after  pull=$pullnote  v$ver  rc=$rc  deploy=$dep"
  say "    drift: $drift"
  say "    dmg:   $dmg"
done
say "craft-all done $(ts)"
