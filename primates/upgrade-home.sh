#!/usr/bin/env bash
# upgrade-home.sh — sync the repo's dotfiles into a primate's persistent <name>-home volume.
#
# Runs INSIDE a throwaway codemonkey:latest container, as root, with:
#   --volume "<repo root>:/opt/user-jhunt:ro"   (the source of truth for every file copied here)
#   --volume "<name>-home:/home/codemonkey"     (the volume being upgraded)
#   --env    "PRIMATE=<name>"                   (drives the per-image blocks at the bottom)
#
# Both callers — `primate-upgrade` in ../zfuncs and `make <name>.upgrade` in ./Makefile — invoke
# it as `bash /opt/user-jhunt/primates/upgrade-home.sh`, so the mounted file's execute bit is
# irrelevant and there is exactly ONE copy of this logic. It used to be duplicated inline in both
# callers, which is how the opencode.json block below came to exist in only one of them.
set -euo pipefail

SRC=/opt/user-jhunt
HOME=/home/codemonkey

# Assert the repo mount actually arrived before touching anything. The likely way it does not:
# running `make upgrade` / `primate-upgrade` from INSIDE a primate, where `--volume "$REPO_ROOT:..."`
# is interpreted by the DAEMON HOST — a container-local path there is an empty host-created dir, not
# the repo (see CLAUDE.md "Docker-out-of-Docker"). Both callers now translate with hostpath, so this
# is the backstop: fail before the first cp, not halfway through, and say what is actually wrong.
for __req in zshrc.template zfuncs jjh.zsh-theme; do
  [ -f "$SRC/$__req" ] || {
    echo "ERROR: $SRC/$__req missing — the repo mount at $SRC is empty or is not this repo." >&2
    echo "       Bind mounts resolve on the Docker DAEMON HOST: from inside a primate the source" >&2
    echo "       path must be a HOST path (see hostpath / \$HOST_WORKSPACE). Refusing to write a" >&2
    echo "       partial upgrade into the home volume." >&2
    exit 3
  }
done

# Ownership repair on EVERY exit path, not just the happy one. This script runs as root, and
# set -euo pipefail means any failure aborts partway — leaving $HOME and every file copied so far
# root:root. That used to self-heal at the next login, when zshrc.template blanket-chowned any
# $HOME child not owned by codemonkey; F6 correctly narrowed that to ~/workspace, so the repair no
# longer exists and this script has to not create the damage in the first place.
trap 'chown -R codemonkey:codemonkey "$HOME" 2>/dev/null || true' EXIT

# dotfiles
cp "$SRC/zaliases"       "$HOME/.zaliases"
cp "$SRC/zbase"          "$HOME/.zbase"
cp "$SRC/zprofile"       "$HOME/.zprofile"
[ -f "$SRC/gitconfig" ] && cp "$SRC/gitconfig" "$HOME/.gitconfig"
cp "$SRC/gitignore"      "$HOME/.gitignore"
cp "$SRC/vimrc"          "$HOME/.vimrc"
cp "$SRC/toprc"          "$HOME/.toprc"
cp "$SRC/tmux.conf"      "$HOME/.tmux.conf"
cp "$SRC/zshrc.template" "$HOME/.zshrc"
cp "$SRC/zfuncs"         "$HOME/.zfuncs"

# ~/.zfuncs is a standalone copy in here — there is no sibling bin/ and setup never runs inside a
# primate, so primate-pull would be unreachable and `primate <img>` inside a primate could not pull
# anything. Put it on PATH the same way the host does.
mkdir -p "$HOME/.local/bin"
cp "$SRC/bin/primate-pull" "$HOME/.local/bin/primate-pull"
chmod +x "$HOME/.local/bin/primate-pull"

# oh-my-zsh update
if [ -d "$HOME/.oh-my-zsh" ]; then
  git -C "$HOME/.oh-my-zsh" pull --quiet 2>/dev/null || true
  for plugin in zsh-autosuggestions zsh-completions zsh-syntax-highlighting; do
    if [ -d "$HOME/.oh-my-zsh/custom/plugins/$plugin" ]; then
      git -C "$HOME/.oh-my-zsh/custom/plugins/$plugin" pull --quiet 2>/dev/null || true
    fi
  done
fi

# oh-my-zsh theme
mkdir -p "$HOME/.oh-my-zsh/custom/themes"
cp "$SRC/jjh.zsh-theme" "$HOME/.oh-my-zsh/custom/themes/jjh.zsh-theme"

# claude config
if [ -d "$SRC/claude" ]; then
  mkdir -p "$HOME/.claude/commands"
  cp "$SRC/claude/settings.json" "$HOME/.claude/settings.json"
  [ -f "$SRC/claude/CLAUDE.md" ] && cp "$SRC/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md"
  cp "$SRC/claude/commands/"* "$HOME/.claude/commands/" 2>/dev/null || true
fi

# Image-baked ~/.config files are shadowed by the persistent home volume, so a rebuild alone
# can't refresh them — sync them here too. opencode.json carries the real model + MCP server
# config; it is gitignored and lives SOPS+age-encrypted in hemlighet (the public image ships
# only opencode.json.example). Decrypt it first (see README) — the [ -f ] guard means this is
# skipped and the image's placeholder stands if the real file isn't present.
if [ "${PRIMATE:-}" = "opencode" ] && [ -f "$SRC/primates/opencode.json" ]; then
  mkdir -p "$HOME/.config/opencode"
  cp "$SRC/primates/opencode.json" "$HOME/.config/opencode/opencode.json"
fi

# ownership is fixed by the EXIT trap above, on success and on failure alike.
