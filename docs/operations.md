# Operations — recovery paths and failure modes

Daily-usage answers that are true by construction; nothing here is a
workaround for a bug.

## Undoing a lane
The express lane is not a trapdoor: recording a `full` disposition makes
the chain walk require the full chain again, and the task resumes at the
first artifact it never had (REFINING). Nothing is lost — the ledger and
review already produced stay valid, and the express review's approval is
superseded by the full chain's own review. This is also what an express
`return-to-plan` verdict means.

Going the other way — full to express — is possible but rarely useful:
the artifacts already exist, so nothing is saved. There is no way to
un-consent.

## Undoing a bypass (historical)
`pipeline decide bypass` was retired in D22; the express lane replaced it
and keeps adjudication. Tasks bypassed before that change still resolve to
BYPASSED and still extract with outcome `bypassed` — decisions are
append-only history and the reader is kept for exactly that reason. There
is no undo: a bypass pins the immutable request, so its hash always
matches. Recovery is a new task with the same body (`/task add`, paste or
re-fetch the request), which today runs express and gets reviewed.

## Abandoning a task
There is no ABANDONED status. The files are the state, so recovery is
deletion: `rm -rf .dev/tasks/<id>` (and its branch, if any). Nothing
else references the task; `task list` and hooks recover instantly. If
the task produced telemetry already (merged/bypassed), the record stays
— history is append-only.

## Corrupted decisions.jsonl lines
Tolerated by design (strict append, tolerant read): bad lines are
skipped and surfaced as `warnings` on the Frontier and in
`pipeline status --json`. Fix by removing the corrupt line if it
bothers you; never rewrite valid lines.

## Consent against a stale artifact
Harmless: consent pins current bytes, but STALE outranks the gates, so
the chain must be repaired first and the frontier tells you so.

## Post-review commits (diff currency)
See D15: the validator does not police the review's diff pin (git stays
outside the product). /work verifies at gate 3 and offers /review on
mismatch. If you merge anyway, that is a human decision the record
preserves.

## Hooks and PATH
Hooks prefer the `pipeline` binary on PATH and fall back to module
invocation; the guard hook fails open outside a pipeline repo. If a
hook seems inert, check `which pipeline`.
