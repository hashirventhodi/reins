---
description: Escape hatch - run only the Execution Contract for a task. Usage - /implement <task-id>
---
Check `python3 ~/.claude/pipeline/core/pipeline_cli.py status $ARGUMENTS --json` first; if next_contract is not
'execution', warn (do not block) that this is out of order. Then invoke the
execution-contract skill for $ARGUMENTS.
