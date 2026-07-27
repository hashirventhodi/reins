# Installation (fresh machine)

Requirements: Python ≥ 3.9, git. Zero dependencies — nothing is
pip-installed, nothing lands on PATH (D30).

    git clone https://github.com/hashirventhodi/reins ~/Code/tools/reins
    cd ~/Code/tools/reins
    ./install.sh                  # idempotent; honors $CLAUDE_HOME
    python3 scripts/selftest.py   # deployment acceptance: proves the core
                                  # derives deterministically on this machine

What install.sh does (and ALL it does):
- symlinks runtime/claude/skills/*  -> ~/.claude/skills/
- symlinks runtime/claude/commands/*.md -> ~/.claude/commands/
- symlinks runtime/claude/agents/reviewer.md -> ~/.claude/agents/
- symlinks contracts/ -> ~/.claude/pipeline/contracts
- symlinks the repo itself -> ~/.claude/pipeline/core

The last symlink is the whole invocation story: every command, skill and
hook calls `python3 ~/.claude/pipeline/core/pipeline_cli.py <cmd>` — no
PATH entry, no venv, no pip. Non-Claude runtimes (Codex, CI) point
`$REINS_HOME` at any checkout and use the same entry point.

Verify the runtime surface (in Claude Code, inside any repo after
`python3 ~/.claude/pipeline/core/pipeline_cli.py init`): `/pipeline-task`,
`/pipeline-work`, and `/pipeline-status` should be available, and `/pipeline-task add hello world`
should print a task id.

Verify the API layer (optional):

    python3 ~/.claude/pipeline/core/pipeline_cli.py --help
    python3 -m pytest -q          # 339 tests, ~10s (dev; needs pytest)

Uninstall (complete): remove the symlinks above and the clone. Nothing
else is written anywhere on the machine.
