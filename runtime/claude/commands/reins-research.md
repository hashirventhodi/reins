---
description: Escape hatch - run only the Findings Contract for a task. Usage - /reins-research <task-id>
---
Check `python3 ~/.claude/reins/core/reins_cli.py status $ARGUMENTS --json` first; if next_contract is not
'findings', warn (do not block) that this is out of order. Then invoke the
findings-contract skill for $ARGUMENTS.
