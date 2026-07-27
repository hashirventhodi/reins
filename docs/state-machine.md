# State Machine — Normative Reference

This document is normative for every runtime binding. Behavior is
implemented in `pipeline/frontier.py` and enforced by
`tests/test_frontier.py`; if this document and the code ever disagree,
that is a bug of the same severity as schema/contract drift (R1).

## Statuses (15)

| Status | Meaning | next_contract | Human needed |
|---|---|---|---|
| INVALID | an artifact or the task violates the type system | none | yes (fix) |
| BYPASSED | valid bypass decision (historical only — creation retired in D22; the express lane replaced it) | none | terminal |
| DONE | merged decision recorded | none | terminal |
| STALE | a pinned upstream changed or is transitively stale | producer of first stale artifact | no |
| BLOCKED | escalation with no later `returned` routing | none | yes (route) |
| RETURNED | pending backward routing (decision or review verdict) | routing target | no |
| AWAITING_INTENT_CONSENT | fresh intent.md without currently-valid consent | none | yes (gate 1) |
| AWAITING_PLAN_APPROVAL | fresh plan.md without currently-valid approval | none | yes (gate 2) |
| NEW | only request.md exists and the decision log is empty | intent | no |
| REFINING | intent.md missing, log non-empty | intent | no |
| RESEARCHING | findings.md is the first missing artifact | findings | no |
| PLANNING | plan.md is the first missing artifact | planning | no |
| IMPLEMENTING | ledger.md is the first missing artifact | execution | no |
| REVIEWING | review.md is the first missing artifact | review | no |
| UNVERIFIED | chain complete and approved, but no passing check covers the reviewed tree | none | no (the runtime runs the checks) |
| AWAITING_MERGE | full fresh chain, approving verdict, verified, not merged | none | yes (gate 3) |

## Precedence (normative; first match wins)

| Rank | Status | Beats |
|---|---|---|
| 1 | INVALID | everything — no contract may run against invalid state |
| 2 | BYPASSED | everything below (terminal) |
| 3 | DONE | everything below (terminal; incl. STALE — post-merge edits to task artifacts are irrelevant) |
| 4 | STALE | BLOCKED, RETURNED, gates, progression — repair the chain before interpreting anything else |
| 5 | BLOCKED | RETURNED, gates, progression — an unrouted escalation halts everything |
| 6 | RETURNED | gates, progression |
| 7 | AWAITING_INTENT_CONSENT, then AWAITING_PLAN_APPROVAL | progression |
| 8 | chain walk (NEW/REFINING/RESEARCHING/PLANNING/IMPLEMENTING/REVIEWING) | UNVERIFIED, AWAITING_MERGE |
| 9 | UNVERIFIED | AWAITING_MERGE — an unverified chain never opens gate 3 |
| 10 | AWAITING_MERGE | — |

Pairwise tests pin ranks 1 vs 4, 3 vs 4, and 4 vs 5
(`test_precedence_*` in tests/test_frontier.py).

## Lanes (D21)

A `disposition` decision records the lane in force; **absent disposition
means `full`**, so an undisposed task behaves exactly as it always has.
The lane selects which artifacts the chain walk requires — it parameterises
the walk, it does not fork it, and it changes nothing else:

| Lane | Required artifacts | Human stops |
|---|---|---|
| `express` | request → ledger → review | 1 (merge) |
| `full` | request → intent → findings → plan → ledger → review | 3 (gates 1–3) |

Consequences worth stating:

- **Gates 1 and 2 are not suppressed on `express`; they cannot fire.** Their
  rule is "intent.md/plan.md exists and is fresh but carries no valid
  consent", and on this lane those files never exist. There is no
  lane-specific gate logic anywhere.
- **The always-on obligations are lane-independent.** Disclosure (`ledger`,
  where an empty Entries list still asserts "the diff matches the request"),
  adjudication (`review`, never waived), and verification (D19) apply
  identically. `express` buys fewer *consent stops*, not less checking.
- **`express` substitutes rather than waives:** the immutable `request.md`
  is the standard the review adjudicates against, in place of a confirmed
  intent and an approved plan. Provenance stays total — the alternate pin
  set is still a complete, hash-pinned set.
- **Escalation needs no new machinery.** A change that outgrows the lane is
  re-disposed to `full`; the walk then requires the full chain and the task
  resumes at the first artifact it never had (REFINING). An express review
  returning `return-to-plan` means exactly this.
- The validator accepts either pin set because it is file-only and cannot
  know the lane; whether a shape is *legal for this task* is the frontier's
  question, since only it reads the decision log.

## Clearing rules (deterministic, no hidden state)

- **Consent (D3):** the latest `intent_confirmed`/`plan_approved` counts
  iff its pinned hash equals the current file bytes. Any edit voids it
  and reopens the gate.
- **Escalation:** resolved by any later `returned` decision in the log;
  until then BLOCKED.
- **Decision-based return:** pending until the target contract's
  artifact carries `produced_at` strictly later than the decision `ts`
  (ISO-8601 UTC strings; lexical comparison — no clocks are consulted).
- **Verdict-based return** (`return-to-implement`/`return-to-plan` in a
  fresh review): needs no clearing rule — regenerating the target stales
  the review (its pin changes), and STALE precedence produces the
  re-implement-then-re-review flow.
- **Diff currency (D15):** the validator checks the review's virtual `diff`
  pin for *format* only, never for currency — deciding whether a tree id is
  still current needs git, which stays outside the product (D12). The
  runtime verifies it at gate 3 by mechanical comparison; commits after
  review surface as a warning and a /review offer, not silent
  AWAITING_MERGE.
- **Verification (D19):** a task leaves UNVERIFIED when, for every verifier
  that has recorded against the **reviewed tree**, the latest record is
  `pass`. Three consequences worth stating: a check against a different
  tree does not count (the `tree_ref`/`diff` anchor is what ties a
  verification to what was actually reviewed); re-running a verifier to a
  pass clears an earlier failure, because only the latest record per
  verifier is consulted, in log order; and `inconclusive` is not a pass, so
  a checker that could not reach an answer holds the gate rather than
  silently opening it.
- **Reference formats (D16):** content artifacts pin `sha256:<64 hex>` over
  exact file bytes; virtual artifacts pin `git:<object id>` (40 hex on sha1
  repositories, 64 on sha256 ones). The two identities are distinct and not
  interchangeable — `hash-format` rejects each in the other's position, and
  a git object id is never re-hashed to imitate a content hash.
- **Bypass:** valid iff its pinned request hash matches request.md
  (always true in practice: request.md is immutable).

## Determinism guarantee

`frontier(task_dir)` is a pure function of (artifact bytes,
decisions.jsonl bytes). Identical inputs produce byte-identical
`to_json()` output regardless of directory location; the Frontier
carries the task directory *name*, never a path, and no wall-clock time.
This is what makes `/work` idempotent and resumable, and what future
runtimes may rely on.
