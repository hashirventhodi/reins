---
description: Escape hatch - run only the Review Contract via the reviewer agent. Usage - /reins-review <task-id>
---
Check `python3 ~/.claude/reins/core/reins_cli.py status $ARGUMENTS --json`; if next_contract is not 'review',
warn (do not block). Then invoke the reviewer subagent for $ARGUMENTS, passing
only file paths (.dev/tasks/$ARGUMENTS/{intent,plan,ledger}.md — express lane:
{request,ledger}.md) and the explicit diff base — never session content.

The base is the commit the task branch was cut from: take it from the ledger if
it is recorded there, otherwise from `git merge-base` against the branch the
work actually started on. Do not pass `main` because it is usual, and do not
leave the base out — the reviewer refuses without one, which is the intended
behavior, not an error to work around.
