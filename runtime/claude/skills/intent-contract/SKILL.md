---
name: intent-contract
description: Produce intent.md from a task's immutable request.md. Use when the /work orchestrator or /refine invokes the Intent Contract for a pipeline task.
---
Read and follow exactly: ~/.claude/pipeline/contracts/intent.md
Write the artifact to .dev/tasks/<task>/intent.md, then set frontmatter only via:
  python3 ~/.claude/pipeline/core/pipeline_cli.py frontmatter <file> --set pipeline=1 --set contract=intent --set task=<task> --set produced_at=<now UTC ISO> --pin request=.dev/tasks/<task>/request.md
Never hand-write hashes. If this task looks sub-threshold, that is a PROPOSAL
and never self-recorded: the lane is chosen before this contract runs, from
`python3 ~/.claude/pipeline/core/pipeline_cli.py floor` plus an explicit human reply, and recorded with
`python3 ~/.claude/pipeline/core/pipeline_cli.py decide disposition`. Say so and STOP rather than deciding it here.
Finish by running: python3 ~/.claude/pipeline/core/pipeline_cli.py validate <task> — fix any violations it reports.
