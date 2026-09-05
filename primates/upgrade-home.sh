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
# ~/.zfuncs is a COPY in here, not the repo symlink, so its fleet consumers cannot reach
# $SRC/primates/fleet.conf at runtime. Install the inventory beside it, derived from the same
# single source — never a second hand-maintained list.
cp "$SRC/primates/fleet.conf" "$HOME/.fleet.conf"

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

# fix ownership
chown -R codemonkey:codemonkey "$HOME"
