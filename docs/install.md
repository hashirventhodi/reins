# Installation (fresh machine)

Requirements: Python ≥ 3.9 and git. **Zero dependencies** — nothing is
pip-installed and nothing lands on PATH (D30).

## Option A — skills.sh (one command)

A root `SKILL.md` makes the repository itself one skill, so this copies
the *entire* system — core, contract texts, runtime, and the executable
fixtures — into `~/.claude/skills/reins` (D34):

    npx skills add hashirventhodi/reins -g

Then invoke `/reins` in your agent once. It runs the two steps below
from the copy it just installed — no network, no clone:

    sh ~/.claude/skills/reins/install.sh
    python3 ~/.claude/skills/reins/scripts/selftest.py

## Option B — git checkout

Identical result; pick this if you intend to work on Reins itself.

    git clone https://github.com/hashirventhodi/reins ~/Code/tools/reins
    cd ~/Code/tools/reins
    ./install.sh                  # idempotent; honors $CLAUDE_HOME
    python3 scripts/selftest.py   # deployment acceptance: proves the core
                                  # derives deterministically on this machine

## What install.sh does (and ALL it does)

- symlinks `runtime/claude/skills/*` -> `~/.claude/skills/`
- symlinks `runtime/claude/commands/reins-*.md` -> `~/.claude/commands/`
- symlinks `runtime/claude/agents/reviewer.md` -> `~/.claude/agents/`
- symlinks `contracts/` -> `~/.claude/reins/contracts`
- symlinks the checkout itself -> `~/.claude/reins/core`
- removes stale unprefixed command links left by installs from before the
  `/reins-*` rename (D31), so nothing shadows the new names

The `core` symlink is the whole invocation story: every command, skill and
hook calls `python3 ~/.claude/reins/core/reins_cli.py <cmd>` — no
PATH entry, no venv, no pip. Non-Claude runtimes (Codex, CI) point
`$REINS_HOME` at any checkout and use the same entry point.

If `~/.claude/commands` is itself a symlink (into a dotfiles repo, say),
the command links are written through it — install.sh says so on
completion.

## Verify

The runtime surface, in Claude Code, inside any repo after
`/reins-init`: `/reins-task`, `/reins-work` and `/reins-status` should
be available, and `/reins-task add hello world` should print a task
id.

The core itself:

    python3 ~/.claude/reins/core/reins_cli.py --help
    python3 ~/.claude/reins/core/scripts/selftest.py   # every line: ok

Contributors also run the development suite from a checkout:

    python3 -m pytest -q          # 340 tests, ~10s (needs pytest)

## Uninstall (complete)

Remove what install.sh created, then the payload:

    rm -rf ~/.claude/reins/core ~/.claude/reins/contracts \
           ~/.claude/agents/reviewer.md ~/.claude/commands/reins-*.md
    rm -rf ~/.claude/skills/{intent,findings,planning,execution,review}-contract
    rm -rf ~/.claude/skills/reins        # option A payload
    # option B: also delete the clone, e.g. ~/Code/tools/reins

Per-repository state (`.dev/`, `telemetry.jsonl`, `.claude/hooks/`) is
removed separately and is fully reversible — see docs/migration.md.
Nothing else is written anywhere on the machine.
