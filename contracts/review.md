---
contract: review
consumes: [intent, plan, ledger, diff]
consumes_express: [request, ledger, diff]
produces: review
gate: null
backward: [execution, planning]
verdicts: [approve, approve-with-fixes, return-to-implement, return-to-plan]
artifact_sections:
  - Fidelity
  - Findings
  - Coverage
  - Verdict
telemetry:
  - verdict_sequence
  - undeclared_deviations_found
---
# Review Contract

**The contract:** review is performed from *clean context* — no access to
the implementer's session, reasoning, or intent beyond the written
artifacts — and adjudicates the diff against the approved plan and
deviation ledger before judging code quality. Bias independence is the
point: the reviewer must be structurally unable to inherit the author's
blind spots. No phase may depend on anything another phase didn't write
down; this contract is where that property earns its keep.

**Inputs:** the diff (pinned as the branch head tree hash), `plan.md`,
`ledger.md`, and `intent.md` (for validation, below). Execution posture:
fresh session or read-only reviewer agent; file paths in, never session
content.

**On the express lane** the standard is the immutable `request.md` in place
of a confirmed intent and an approved plan. This contract is never waived —
adjudication from clean context is what the lane is buying — but the
standard is vaguer, so the emphasis shifts: verification asks "does the diff
do what the request literally asked", and the scope question carries most of
the weight. *And nothing else* is the express lane's dominant failure mode,
so an out-of-scope change is a blocking finding here even when it would be
merely a should-fix against an approved plan. A `return-to-plan` verdict on
this lane means the change needs planning it never had: it re-disposes the
task to `full`.

**Artifact — `review.md`:**

- **Fidelity** — does the diff execute the approved plan? Is each ledger
  entry justified? Were any **undeclared** deviations found? The
  undeclared-deviation search is mandatory and its result is reported even
  when empty, as the literal line `undeclared_deviations: none` or
  `undeclared_deviations: found`. This is the check that makes the ledger
  honest. Fidelity also validates against intent: verification asks "does
  this code do what the plan agreed"; validation asks "does the plan's
  outcome serve the confirmed intent's success criteria."
- **Findings** — issues grouped `blocking` / `should-fix` / `nit`, each
  with `file:line` and a concrete suggested fix. No style findings a
  formatter handles. Every blocking finding is actionable as written.
- **Coverage** — what was examined and found sound. Proves the review
  happened; an empty Coverage section invalidates the review.
- **Verdict** — exactly one of:
  - `approve` — merge path opens (gate 3, the merge itself, belongs to
    the human and git, not to this contract).
  - `approve-with-fixes` — named non-blocking fixes; re-review not
    required.
  - `return-to-implement` — plan is sound, execution is not: blocking
    findings or unjustified within-autonomy deviations.
  - `return-to-plan` — the plan itself is invalidated by what
    implementation revealed, or undeclared deviations are plan-level
    (E2-class).

**Quality guarantees:**
- G1. Fidelity section present, with the explicit undeclared-deviation
  result line.
- G2. Verdict/fidelity consistency: `undeclared_deviations: found` cannot
  coexist with `approve`.
- G3. Zero unactionable blocking findings.

**Blocking conditions:** any consumed artifact is stale or missing — a
review of unpinned inputs is void by construction.

**Exit criteria:** verdict issued; for approvals, human concurrence at
merge.

**Backward transitions:** → Execution (`return-to-implement`),
→ Planning (`return-to-plan`). Backward edges carry this review's reasons
as their input.
