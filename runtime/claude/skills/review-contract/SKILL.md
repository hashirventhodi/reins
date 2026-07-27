---
name: review-contract
description: Adjudicate the diff against plan.md, ledger.md and intent.md from clean context, producing review.md. Only the reviewer agent should execute this. Use when the /work orchestrator or /review invokes the Review Contract.
---
Read and follow exactly: ~/.claude/pipeline/contracts/review.md
Your only inputs are intent.md, plan.md, ledger.md and the git diff of the branch. Do not read any session context.
Write .dev/tasks/<task>/review.md, then:
  python3 ~/.claude/pipeline/core/pipeline_cli.py frontmatter <file> --set pipeline=1 --set contract=review --set task=<task> --set produced_at=<now UTC ISO> --pin intent=... --pin plan=... --pin ledger=... --pin diff=git:$(git rev-parse HEAD^{tree})
On the express lane intent.md and plan.md do not exist: pin request, ledger and
diff, and adjudicate the diff against request.md itself. The standard is vaguer,
so scope carries the weight — an out-of-scope change is BLOCKING there.
Never hand-write file hashes. The diff pin is a git object reference, not a
content hash: write it as git:<tree-id> verbatim from git rev-parse, never
re-hashed (D16). Finish with: python3 ~/.claude/pipeline/core/pipeline_cli.py validate <task>.
