# Follow-up tasks

Review often surfaces work that shouldn't block the current task but
shouldn't be forgotten: refactors, debt, coverage, performance,
observability, cleanup, follow-on features. In this architecture that is
**intake, not a phase** — a follow-up is a new root, and the Task Source
abstraction (D9) already covers it: a review of a prior task is simply
another source yielding `(raw_request, source_ref)`.

## Where candidates already live (no new artifact)

The contracts already force follow-up material into four places:
- `findings.md` **Out-of-scope observations** — the mandated disposition
  of the Execution Contract's refactor ban (P1)
- `intent.md` **Non-goals** recorded as deferred
- `review.md` **should-fix / nit findings** left unfixed under
  `approve-with-fixes`
- `ledger.md` entries whose `plan_impact` defers work

What v1 adds is the **harvest step**. Harvesting is derivation, so it
lives in the product (D14): `pipeline followups <id> --json` is a pure,
deterministic projection — chain order (intent, findings, ledger,
review; document order within each), mechanical extraction rules
(/defer/i non-goals; every out-of-scope observation; ledger entries with
plan_impact != none; should-fix/nit review findings), exact-normalized
dedup (first occurrence wins, origins accumulate; deliberately no fuzzy
matching), word-boundary titles (<=72 chars), verbatim bodies plus a
fixed origin line, and `already_created` detection so re-runs never
re-offer what exists. `/pipeline-followups <task-id>` presents that list and
relays the human's explicit selection by invoking `pipeline task add`
once per selected candidate — title/body extracted from the JSON
mechanically (jq/python, never retyped; `creation_body()` is the
normative byte spec), skipping `already_created` candidates, with the
same-day slug collision in `task add` as the deterministic backstop. The pipeline never touches
external trackers and remains unaware `followup:` means anything.

## The convention (normative for runtimes)

- `--source-ref "followup:<parent-task-id>"`
- request body = the harvested item **verbatim** (byte-exact intake
  applies: the item is the raw request) plus one origin line
- one task per accepted item; nothing created without explicit selection

Traceability is child-side and telemetry-native: `task_ref` already
carries `source_ref` into every record, so lineage is a query (see
docs/queries.md, query 6), not stored state. The decision enum is
unchanged; the frontier is unchanged; PIPELINE_VERSION is unchanged.

## Deferred to v2, pending evidence

A structured `Follow-ups` section in `review.md` is a Tier-2 change
(docs/governance.md): evaluated on merits, with the signal below
pre-registered as the strongest evidence either way. Promotion bar: if a
meaningful share of merged tasks spawn accepted follow-ups **harvested
specifically from the reviewer's fresh-context findings** (rather than
from findings/intent, where authors already record them), the section
has earned first-class status. Query 6 measures it.
