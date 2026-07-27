---
name: planning-contract
description: Produce plan.md from confirmed intent.md and findings.md. Use when the /work orchestrator or /plan invokes the Planning Contract for a pipeline task.
---
Read and follow exactly: ~/.claude/pipeline/contracts/planning.md
Write .dev/tasks/<task>/plan.md, then set frontmatter only via:
  python3 ~/.claude/pipeline/core/pipeline_cli.py frontmatter <file> --set pipeline=1 --set contract=planning --set task=<task> --set produced_at=<now UTC ISO> --pin intent=... --pin findings=...
Never hand-write hashes. Finish with: python3 ~/.claude/pipeline/core/pipeline_cli.py validate <task> — fix violations.
