---
description: Run a task's verifications and record each result. Usage - /pipeline-verify <task-id>
---
Task: $ARGUMENTS. Resolves UNVERIFIED, which is not a human stop. For each check
the plan names — or, on the express lane, each check the request implies:
1. Run it. Capture stdout+stderr to a file; never summarize or retype output.
2. Record it:
   `python3 ~/.claude/pipeline/core/pipeline_cli.py verify $ARGUMENTS --verifier <slug> --tool "<name version>"
    --predicate "<the claim tested>" --verdict pass|fail|inconclusive
    --tree-ref git:$(git rev-parse HEAD^{tree}) --evidence-file <path>
    [--standard-touched]`
3. `--tree-ref` must be the tree the review pins as `diff`; a check against a
   different tree does not count toward the gate.
4. `--standard-touched` iff this diff changed what that verifier judges by — its
   tests, lint rules, or allowlists.
5. The verdict is the MEANING, not the exit code. A checker that could not reach
   an answer is `inconclusive`, never `pass`. Never record a verdict for a check
   you did not run.
