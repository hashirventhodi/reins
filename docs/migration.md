# Migrating an existing repository  (~10 minutes)

Reins is strictly additive. Nothing outside the paths listed in step 2
is created or modified; rollback is deletion.

1. Prerequisite: install per docs/install.md.
2. In the repo root:

       python3 ~/.claude/pipeline/core/pipeline_cli.py init
                                  # creates .dev/tasks/, .dev/config.yaml,
                                  # telemetry.jsonl (empty)
       mkdir -p .claude/hooks
       # ~/.claude/pipeline/core is created by install.sh and points at
       # whichever checkout you installed from, so this works for both the
       # skills.sh and git-checkout installs. $REINS_HOME wins if set.
       CORE="${REINS_HOME:-$HOME/.claude/pipeline/core}"
       cp "$CORE"/runtime/claude/hooks/*.sh .claude/hooks/
       cp "$CORE"/runtime/claude/settings.example.json .claude/settings.json
       printf '.claude/settings.local.json\n' >> .gitignore

3. Set the per-stack post-edit command (the ONLY per-repo tuning), e.g.
   in .claude/settings.json hook env or your shell profile:

       PIPELINE_POST_EDIT_CMD='ruff check --fix {file} && pyright {file}'

4. AGENTS.md / CLAUDE.md are orthogonal to the pipeline and unchanged.
5. In-flight work: finish current branches old-style; new tasks enter
   via `/pipeline-task add`. No artifact back-fill, ever.
6. First task — conversational, in Claude Code: `/pipeline-task add <what you
   want>` then `/pipeline-work <id>`. (The deterministic core underneath is
   the API for runtime authors and no-AI use: docs/cli.md.)

Prerequisite reminder: install Reins first (docs/install.md) — one
command via skills.sh, or a git checkout.

## Rollback (complete, no residue)

    rm -rf .dev/ .claude/hooks/protect-paths.sh .claude/hooks/post-edit-check.sh \
           .claude/hooks/guard-execution-phase.sh telemetry.jsonl
    # restore .claude/settings.json and .gitignore from git:
    git checkout -- .claude/settings.json .gitignore 2>/dev/null || true

The repo is byte-identical to its pre-migration state (verified by
tests/test_m5_acceptance.py::test_A2_A3_migration_happy_path_and_rollback).
