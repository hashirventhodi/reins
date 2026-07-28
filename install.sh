#!/bin/sh
# Install the Claude Code runtime binding as a consumer of the product.
# Idempotent; symlinks so contract edits stay single-sourced (D9).
# Nothing lands on PATH and nothing is pip-installed: the deterministic
# core is invoked by path through the `core` symlink (D30).
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${CLAUDE_HOME:-$HOME/.claude}"

mkdir -p "$DEST/skills" "$DEST/commands" "$DEST/agents" "$DEST/reins"

for skill in "$SRC"/runtime/claude/skills/*; do
  ln -sfn "$skill" "$DEST/skills/$(basename "$skill")"
done
for cmd in "$SRC"/runtime/claude/commands/*.md; do
  ln -sf "$cmd" "$DEST/commands/$(basename "$cmd")"
done
# D35: commands are /reins-* now. Drop links from every earlier naming
# (unprefixed, then pipeline-*) that point into this checkout or dangle
# from a pre-rename install, so nothing shadows the current names.
for name in work task status dispose verify review followups refine \
            research plan implement validate; do
  for link in "$DEST/commands/$name.md" "$DEST/commands/pipeline-$name.md"; do
    [ -L "$link" ] || continue
    target="$(readlink "$link")"
    case "$target" in
      "$SRC"/*|*/contract-pipeline/*|*/contract-runtime/*) rm -f "$link" ;;
    esac
  done
done
# the pre-D35 install directory, superseded by $DEST/reins
if [ -L "$DEST/pipeline/core" ] || [ -L "$DEST/pipeline/contracts" ]; then
  rm -f "$DEST/pipeline/core" "$DEST/pipeline/contracts"
  rmdir "$DEST/pipeline" 2>/dev/null || true
fi
ln -sf "$SRC/runtime/claude/agents/reviewer.md" "$DEST/agents/reviewer.md"
ln -sfn "$SRC/contracts" "$DEST/reins/contracts"
ln -sfn "$SRC" "$DEST/reins/core"

echo "linked skills, commands, reviewer agent, contracts, core -> $DEST"
echo "(if $DEST/commands is itself a symlink, e.g. into a dotfiles repo,"
echo " the command links were written through it)"
echo "verify: python3 \"$DEST/reins/core/reins_cli.py\" --help"
echo "per-project: copy runtime/claude/settings.example.json into"
echo "  <repo>/.claude/settings.json and runtime/claude/hooks/ into"
echo "  <repo>/.claude/hooks/, then run:"
echo "  python3 \"$DEST/reins/core/reins_cli.py\" init"
