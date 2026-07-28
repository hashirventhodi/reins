---
description: Present deterministic follow-up candidates from a finished task; create the ones the human approves. Usage - /reins-followups <task-id>
---
Run `python3 ~/.claude/reins/core/reins_cli.py status $ARGUMENTS --json` first; this is meant for
AWAITING_MERGE or DONE (warn otherwise, do not block).
Run `python3 ~/.claude/reins/core/reins_cli.py followups $ARGUMENTS --json` — never derive candidates
yourself. Present the numbered list (titles + origins), marking any
`already_created`; skip those. Create NOTHING without an explicit human
selection. For each selected candidate, extract title and body from the
JSON MECHANICALLY (jq or python -c, never retyped) and run:
  python3 ~/.claude/reins/core/reins_cli.py task add --title "<candidate.title>" --body-file <tmp file
  containing candidate.body + blank line + "Origin: review of
  $ARGUMENTS"> --source-ref "followup:$ARGUMENTS"
Report the created task IDs. Never create GitHub/Jira issues — this is
local intake only; external trackers are the human's.
