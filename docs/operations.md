# Operations — recovery paths and failure modes

Daily-usage answers that are true by construction; nothing here is a
workaround for a bug.

Command shorthand: `reins <cmd>` below abbreviates the real
invocation, `python3 ~/.claude/reins/core/reins_cli.py <cmd>`
(docs/cli.md). There is no binary of that name on PATH.

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
`reins decide bypass` was retired in D22; the express lane replaced it
and keeps adjudication. Tasks bypassed before that change still resolve to
BYPASSED and still extract with outcome `bypassed` — decisions are
append-only history and the reader is kept for exactly that reason. There
is no undo: a bypass pins the immutable request, so its hash always
matches. Recovery is a new task with the same body (`/reins-task add`, paste or
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
`reins status --json`. Fix by removing the corrupt line if it
bothers you; never rewrite valid lines.

## Consent against a stale artifact
Harmless: consent pins current bytes, but STALE outranks the gates, so
the chain must be repaired first and the frontier tells you so.

## Post-review commits (diff currency)
See D15: the validator does not police the review's diff pin (git stays
outside the product). /reins-work verifies at gate 3 and offers /reins-review on
mismatch. If you merge anyway, that is a human decision the record
preserves.

## Hooks that seem inert
Hooks resolve the core by path, never through PATH (D30): `$REINS_HOME`
if set, else `~/.claude/reins/core`, falling back to `python3 -m
reins.cli` in a development checkout. The guard hook additionally
fails open outside a Reins repo, by design.

If a hook seems inert, check the link the hooks actually use — not
`which reins`, which is expected to print nothing:

    ls -l ~/.claude/reins/core        # must resolve to a checkout
    echo "$REINS_HOME"                   # if set, it wins

A dangling `core` link (checkout moved or deleted) is the usual cause;
re-run `install.sh` from the checkout's new location to repair it.

## The core refuses to start
- `reins requires Python >= 3.9` — the entry point asserts the floor
  before importing anything (D30). Invoke a newer `python3`; nothing
  else is wrong.
- A `line N:` YAML error from `miniyaml` means an artifact strayed
  outside the supported subset (D30) — usually a hand-written fence with
  a construct the pipeline never emits, such as a flow mapping or a
  block scalar. Rewrite the value as a plain or quoted scalar; do not
  reach for a YAML library.

## Selftest fails after regenerating fixtures
`scripts/regen_fixtures.py` rewrites the executable specifications, and
`scripts/selftest.py` byte-compares derived output against the goldens
in `scripts/goldens/`. If a fixture change is intentional and the suite
is green, refreeze with `python3 scripts/selftest.py --regen` and commit
the goldens alongside the fixtures. Never edit a golden by hand.

## Commands are missing or the wrong ones run
Commands are `/reins-*` (D31). If an unprefixed `/work` or `/review`
still resolves, an install from before the rename left a stale link;
re-running `install.sh` removes the ones pointing at a Reins checkout.
Anything else answering to those names belongs to another tool.
