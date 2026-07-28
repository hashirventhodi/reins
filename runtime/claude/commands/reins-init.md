---
description: Set up the current repository for Reins - task store, floor policy, hooks, settings. Usage - /reins-init
---
Per-repository setup. Additive and idempotent: never overwrite an
existing file — report it and let the human decide.

1. `python3 ~/.claude/reins/core/reins_cli.py init` — creates `.dev/tasks/`,
   `.dev/config.yaml` (the starter floor policy) and an empty
   `telemetry.jsonl` **at the repository root**, not under `.dev/`. Files
   that already exist are left untouched. Create nothing yourself: if a
   path is missing, report it rather than filling it in.
2. `CORE="${REINS_HOME:-$HOME/.claude/reins/core}"`, then `mkdir -p
   .claude/hooks` and copy `$CORE/runtime/claude/hooks/*.sh` into it,
   skipping any hook already present.
3. If `.claude/settings.json` is absent, copy
   `$CORE/runtime/claude/settings.example.json` to it. If it exists, show
   what the example adds and STOP for the human — never merge settings
   unasked.
4. Append `.claude/settings.local.json` to `.gitignore` if absent.
5. Report created versus skipped, then run `/reins-policy audit`: every
   preset ships on, so the starter over-governs on purpose and the audit
   is how it gets narrowed deliberately. Mention `PIPELINE_POST_EDIT_CMD`
   as the one other per-repo knob (docs/migration.md).

Then the workflow is `/reins-task add <title>` and `/reins-work <id>`.
