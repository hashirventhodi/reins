---
description: Escape hatch - run only the Planning Contract for a task. Usage - /reins-plan <task-id>
---
Check `python3 ~/.claude/reins/core/reins_cli.py status $ARGUMENTS --json` first; if next_contract is not
'planning', warn (do not block) that this is out of order. Then invoke the
planning-contract skill for $ARGUMENTS.
