---
name: reins
description: Reins - a deterministic contract pipeline governing AI-assisted development - typed contracts, three human approval gates, computed process floor, reproducible telemetry, /reins-* commands. Invoke once after installing to wire the runtime into your agent; also use to re-verify or repair the install.
---

# Reins

Installing this skill delivered the whole system — the deterministic core
(`reins/`, `reins_cli.py`), the canonical contract texts
(`contracts/`), the Claude Code runtime (`runtime/`), and the executable
specifications (`tests/fixtures/`). Nothing else is downloaded; there are
no dependencies and nothing is pip-installed (D30).

Two steps remain, because a skills installer cannot register slash
commands or subagents. Run both from this skill's own directory (the
directory containing this file), then report:

1. `sh <skill-dir>/install.sh` — symlinks into `$CLAUDE_HOME` (default
   `~/.claude`): the twelve `/reins-*` commands, the five contract
   skills, the reviewer agent, `reins/contracts`, and
   `reins/core` (which is how every command reaches the core:
   `python3 ~/.claude/reins/core/reins_cli.py <cmd>`).
2. `python3 <skill-dir>/scripts/selftest.py` — proves the core derives
   deterministically here. Requires Python ≥ 3.9; every line must read
   `ok`.
Then tell the human: the runtime is linked, selftest passed, and the
workflow is `/reins-task add <title>` then `/reins-work <id>`,
with `python3 ~/.claude/reins/core/reins_cli.py init` once per
repository. In a non-Claude runtime, set `$REINS_HOME` to this
directory and invoke `python3 "$REINS_HOME/reins_cli.py" <cmd>`.

Both steps are idempotent; re-run them to repair or update an install.
If either fails, STOP and show the exact command and its output. Never
improvise an alternative: no pip, no PATH edits, no hand-copying files.
The symlink layout is the supported install (D30/D31/D34).
