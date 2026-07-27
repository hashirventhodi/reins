---
name: reins
description: Install or update Reins, the deterministic contract pipeline for AI coding agents - typed contracts, human approval gates, reproducible telemetry, /pipeline-* commands. Run once after adding this skill; it clones the repo and links the full runtime into ~/.claude. Also use to update an existing install or re-verify it.
---

# Reins — install or update

Reins is more than this skill: a deterministic Python core, five contract
skills, twelve `/pipeline-*` commands, a fresh-context reviewer agent,
and canonical contract texts. A skill install alone cannot deliver that,
so this skill bootstraps the real thing (D30: the core travels with its
invoker — nothing is pip-installed, nothing lands on PATH).

Steps (all idempotent; safe to re-run):

1. Clone or update the checkout:
   - If `~/Code/tools/reins` exists and is a git repo: `git -C ~/Code/tools/reins pull --ff-only`
   - Else: `git clone https://github.com/hashirventhodi/reins ~/Code/tools/reins`
2. Link the runtime: `sh ~/Code/tools/reins/install.sh`
   (symlinks skills, `/pipeline-*` commands, the reviewer agent,
   contracts, and the core into `$CLAUDE_HOME`, default `~/.claude`).
3. Prove determinism on this machine: `python3 ~/Code/tools/reins/scripts/selftest.py`
   — requires Python ≥ 3.9; every line must read `ok`.
4. Report to the human: where the checkout lives, that selftest passed,
   and that `/pipeline-task add <title>` then `/pipeline-work <id>` is
   the workflow. Per repository, one-time:
   `python3 ~/.claude/pipeline/core/pipeline_cli.py init`.

If any step fails, STOP and show the exact command and its output — do
not improvise an alternative install (no pip, no PATH edits, no copying
files by hand; the symlink layout is the supported install, D30/D31).
