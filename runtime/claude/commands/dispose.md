---
description: Choose the lane for a task - compute the floor, propose, record the human's decision. Usage - /dispose <task-id>
---
Task: $ARGUMENTS. The lane decides which artifacts the task needs; only a human
may choose it, and never below the computed floor without a recorded reason.
1. Gather facts about the SOURCE change only. Before work: the files you intend
   to touch. After work: `git diff --name-only <base>...HEAD`. Either way EXCLUDE
   the pipeline's own bookkeeping — `.dev/**` and `telemetry.jsonl` are task
   state, not the change under review, and counting them pushes every task to
   `full`. Count added+removed lines over the same filtered set.
2. `printf '%s\n' <paths> | python3 ~/.claude/pipeline/core/pipeline_cli.py floor $ARGUMENTS --lines-changed <n>`
3. Show the floor, every reason it gave, and the lane you propose (at or above
   it). Then STOP. Proposing is yours; deciding is the human's.
4. Only on an explicit human reply:
   `python3 ~/.claude/pipeline/core/pipeline_cli.py decide disposition $ARGUMENTS --lane <lane> --floor <floor>`
   A lane BELOW the floor also needs `--reason`; it is recorded as an override
   and counted in telemetry. Never record a lane the human did not state.
