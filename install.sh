#!/bin/sh
# Install the Claude Code runtime binding as a consumer of the product.
# Idempotent; symlinks so contract edits stay single-sourced (D9).
# Nothing lands on PATH and nothing is pip-installed: the deterministic
# core is invoked by path through the `core` symlink (D30).
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${CLAUDE_HOME:-$HOME/.claude}"

mkdir -p "$DEST/skills" "$DEST/commands" "$DEST/agents" "$DEST/pipeline"

for skill in "$SRC"/runtime/claude/skills/*; do
  ln -sfn "$skill" "$DEST/skills/$(basename "$skill")"
done
for cmd in "$SRC"/runtime/claude/commands/*.md; do
  ln -sf "$cmd" "$DEST/commands/$(basename "$cmd")"
done
ln -sf "$SRC/runtime/claude/agents/reviewer.md" "$DEST/agents/reviewer.md"
ln -sfn "$SRC/contracts" "$DEST/pipeline/contracts"
ln -sfn "$SRC" "$DEST/pipeline/core"

echo "linked skills, commands, reviewer agent, contracts, core -> $DEST"
echo "(if $DEST/commands is itself a symlink, e.g. into a dotfiles repo,"
echo " the command links were written through it)"
echo "verify: python3 \"$DEST/pipeline/core/pipeline_cli.py\" --help"
echo "per-project: copy runtime/claude/settings.example.json into"
echo "  <repo>/.claude/settings.json and runtime/claude/hooks/ into"
echo "  <repo>/.claude/hooks/, then run:"
echo "  python3 \"$DEST/pipeline/core/pipeline_cli.py\" init"
