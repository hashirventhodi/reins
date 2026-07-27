---
description: Manage pipeline work items. Usage - /pipeline-task add <title> | /pipeline-task list | /pipeline-task show <id>
---
$ARGUMENTS. For `add`: acquire the request text first — if the user gave a
reference like gh:123, fetch the issue body with `gh issue view 123 --json body`
(or the relevant MCP tool) and pass it VERBATIM, byte-exact, no normalization:
`python3 ~/.claude/pipeline/core/pipeline_cli.py task add --title "..." --body-file <tmp> --source-ref gh:123`.
Zero refinement at capture. For list/show: run `python3 ~/.claude/pipeline/core/pipeline_cli.py task list|show` and
present the output plainly.
