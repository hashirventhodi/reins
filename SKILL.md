---
name: reins
description: Reins - a deterministic contract pipeline governing AI-assisted development - typed contracts, three human approval gates, computed process floor, reproducible telemetry, /pipeline-* commands. Invoke once after installing to wire the runtime into your agent; also use to re-verify or repair the install.
---

# Reins

Installing this skill delivered the whole system — the deterministic core
(`pipeline/`, `pipeline_cli.py`), the canonical contract texts
(`contracts/`), the Claude Code runtime (`runtime/`), and the executable
specifications (`tests/fixtures/`). Nothing else is downloaded; there are
no dependencies and nothing is pip-installed (D30).

One wiring step remains, because a skills installer cannot register
slash commands or subagents. Run it from this skill's own directory
(the directory containing this file):

1. `sh <skill-dir>/install.sh` — symlinks into `$CLAUDE_HOME` (default
   `~/.claude`): the twelve `/pipeline-*` commands, the five contract
   skills, the reviewer agent, `pipeline/contracts`, and
   `pipeline/core` (which is how every command reaches the core:
   `python3 ~/.claude/pipeline/core/pipeline_cli.py <cmd>`).
2. `python3 <skill-dir>/scripts/selftest.py` — proves the core derives
   deterministically here. Requires Python ≥ 3.9; every line must read
   `ok`.
3. Report to the human: that the runtime is linked, that selftest
   passed, and the workflow — `/pipeline-task add <title>` then
   `/pipeline-work <id>`, with `python3
   ~/.claude/pipeline/core/pipeline_cli.py init` once per repository.

Both steps are idempotent; re-run them to repair or update an install.
If either fails, STOP and show the exact command and its output. Never
improvise an alternative: no pip, no PATH edits, no hand-copying files.
The symlink layout is the supported install (D30/D31/D34).
