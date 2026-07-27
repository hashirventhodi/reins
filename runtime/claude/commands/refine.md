---
description: Escape hatch - run only the Intent Contract for a task. Usage - /refine <task-id>
---
Check `python3 ~/.claude/pipeline/core/pipeline_cli.py status $ARGUMENTS --json` first; if next_contract is not
'intent', warn (do not block) that this is out of order. Then invoke the
intent-contract skill for $ARGUMENTS.
