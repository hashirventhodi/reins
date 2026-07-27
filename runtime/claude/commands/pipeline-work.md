---
description: Run the contract pipeline for a task, stopping only at human gates, escalations, or completion. Usage - /pipeline-work <task-id>
---
Task: $ARGUMENTS. Loop (normative; blueprint §6):
1. Run `python3 ~/.claude/pipeline/core/pipeline_cli.py status $ARGUMENTS --json` and dispatch on status:
   - Before the first contract, if the log holds no disposition: run /pipeline-dispose.
     The lane decides which artifacts are required; the human decides the lane.
   - NEW/REFINING/RESEARCHING/PLANNING/IMPLEMENTING/REVIEWING/STALE/RETURNED:
     invoke the skill for next_contract (review ALWAYS via the reviewer subagent
     with file paths and the explicit diff base — never `main` by default; see
     /pipeline-review), then `python3 ~/.claude/pipeline/core/pipeline_cli.py validate $ARGUMENTS`; on violations,
     quote them to the same skill to fix — at most 2 correction rounds, then STOP
     and report as blocked.
   - AWAITING_INTENT_CONSENT / AWAITING_PLAN_APPROVAL: STOP. Record the current
     hash (`python3 ~/.claude/pipeline/core/pipeline_cli.py hash <artifact>`), show the artifact, ask for approval or
     edits. Only on explicit human yes: re-hash; if changed pass --edited:
     `python3 ~/.claude/pipeline/core/pipeline_cli.py consent intent|plan $ARGUMENTS [--edited]`, then continue the loop.
     Present these gates one at a time: confirming intent after a plan exists
     anchors the human to it, which is what gate 1 exists to prevent.
   - UNVERIFIED: run /pipeline-verify, then continue. Mechanical, not a human stop.
   - BLOCKED: STOP. Present the escalation; on the human's routing run
     `python3 ~/.claude/pipeline/core/pipeline_cli.py decide returned $ARGUMENTS --to <contract> --reason "..."`, continue.
   - AWAITING_MERGE: STOP. Diff currency (D15): compare the review's diff pin
     against `git rev-parse HEAD^{tree}` — a mismatch means commits landed after
     review; warn and offer /pipeline-review. Then `python3 ~/.claude/pipeline/core/pipeline_cli.py floor-check $ARGUMENTS` over
     the SOURCE paths (filtered as in /pipeline-dispose): a lane violation must be
     resolved — escalate the lane or record an override — before merge. Then
     report and offer /pipeline-followups.
   - BYPASSED / DONE / INVALID: STOP and report; for DONE offer
     `/pipeline-followups $ARGUMENTS`.
2. Never compute status yourself, never write artifact frontmatter directly, and
   never record a consent or a bypass without an explicit human reply in-session.
