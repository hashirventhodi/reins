---
name: findings-contract
description: Produce findings.md from a confirmed intent.md by investigating the codebase. Use when the /work orchestrator or /research invokes the Findings Contract for a pipeline task.
---
Read and follow exactly: ~/.claude/pipeline/contracts/findings.md
Write .dev/tasks/<task>/findings.md, then set frontmatter only via:
  python3 ~/.claude/pipeline/core/pipeline_cli.py frontmatter <file> --set pipeline=1 --set contract=findings --set task=<task> --set produced_at=<now UTC ISO> --pin request=.dev/tasks/<task>/request.md --pin intent=.dev/tasks/<task>/intent.md
Never hand-write hashes. Finish with: python3 ~/.claude/pipeline/core/pipeline_cli.py validate <task> — fix violations.
