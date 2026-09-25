#!/usr/bin/env bash
# Install the 007 agent skills for Claude and Kiro. The ONE definition of "how skills install":
# the Makefile's `install` target delegates here (host `setup` path), and primates/upgrade-home.sh
# calls it directly to populate a home volume — so the same logic runs on host and in the
# in-container sync, and no code-monkeys Makefile is ever invoked from inside a container.
#
# Each skill (a directory holding a SKILL.md) is copied into $HOME/.local/share/agent-skills and
# symlinked into ~/.claude/skills and ~/.kiro/skills. Keyed off $HOME, so pointing HOME at a mounted
# volume installs into that volume. Support dirs without a SKILL.md (scripts/, tests/, skills-ref/)
# are skipped by construction.
set -euo pipefail

# The skills root is this script's parent dir (scripts/..), so the install is independent of $PWD.
SKILLS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="$HOME/.local/share/agent-skills"
CLAUDE_SKILLS="$HOME/.claude/skills"
KIRO_SKILLS="$HOME/.kiro/skills"

mkdir -p "$INSTALL_DIR" "$CLAUDE_SKILLS" "$KIRO_SKILLS"

for skillmd in "$SKILLS_ROOT"/*/SKILL.md; do
  [ -f "$skillmd" ] || continue          # no SKILL.md dirs, or the glob matching nothing
  dir="$(dirname "$skillmd")"
  skill="$(basename "$dir")"
  rm -rf "$INSTALL_DIR/$skill"
  cp -R "$dir" "$INSTALL_DIR/$skill"
  ln -sfn "$INSTALL_DIR/$skill" "$CLAUDE_SKILLS/$skill"
  ln -sfn "$INSTALL_DIR/$skill" "$KIRO_SKILLS/$skill"
  echo "Installed $skill"
done

echo ""
echo "Installed to: $INSTALL_DIR/"
echo "Symlinked from:"
echo "  Claude:  $CLAUDE_SKILLS/"
echo "  Kiro:    $KIRO_SKILLS/"
