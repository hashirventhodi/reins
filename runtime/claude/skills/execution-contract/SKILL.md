---
name: execution-contract
description: Execute an approved plan.md faithfully, producing the diff and ledger.md, honoring escalation triggers E1-E5 and prohibitions P1-P4. Use when the /pipeline-work orchestrator or /pipeline-implement invokes the Execution Contract.
---
Read and follow exactly: ~/.claude/pipeline/contracts/execution.md
On any escalation trigger STOP and run: python3 ~/.claude/pipeline/core/pipeline_cli.py decide escalation <task> --trigger E# --from execution --detail "...", then end your turn.
Write .dev/tasks/<task>/ledger.md (empty ledger is the yaml list []), then:
  python3 ~/.claude/pipeline/core/pipeline_cli.py frontmatter <file> --set pipeline=1 --set contract=execution --set task=<task> --set produced_at=<now UTC ISO> --pin plan=.dev/tasks/<task>/plan.md
On the express lane there is no plan: pin request instead of plan, and the empty
ledger claims the diff does what the request asked and nothing else. E1-E4 name
planning, which does not exist there — any of them means the change outgrew the
lane, so STOP and say it needs re-disposing to full.
Never hand-write hashes. Finish with: python3 ~/.claude/pipeline/core/pipeline_cli.py validate <task> — fix violations.
