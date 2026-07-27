---
contract: execution
consumes: [plan]
consumes_express: [request]
produces: ledger
gate: null
backward: [planning]
escalations: [E1, E2, E3, E4, E5]
artifact_sections:
  - Entries
telemetry:
  - escalations
  - ledger_entries
  - self_corrections
---
# Execution Contract

**The contract:** execution is *faithful*: the approved plan is carried
out within declared autonomy boundaries, every divergence is recorded in
the deviation ledger, and defined trigger conditions halt execution and
route backward. This contract contains engineering policy — stopping
rules, prohibitions, and one artifact — not implementation advice.

**Inputs:** approved `plan.md`. Outputs: the diff (via git) plus
`ledger.md`.

**On the express lane** the governing document is the immutable `request.md`
itself: no plan exists, so the ledger pins the request instead. Everything
below is unchanged — the autonomy boundaries, the escalation triggers, the
prohibitions, and the ledger's meaning all apply identically. An empty
ledger still asserts a claim; on this lane the claim is "the diff does what
the request asked and nothing else", and Review tests it. E1–E4 name
`planning`, which does not exist here: on the express lane any of them means
the change has outgrown the lane, so the task is re-disposed to `full` and
the plan is written before work continues.

**Autonomy boundaries (may act without asking):** executing plan steps and
their named verifications; mechanical choices the plan does not constrain
(naming, file placement consistent with existing patterns); fixing defects
*introduced by this work*.

**Escalation triggers (must stop and route):**
- **E1** — a plan assumption is discovered false. → planning
- **E2** — a step requires changing a public interface, a persisted data
  shape, or adding a dependency not named in the plan. → planning
- **E3** — a step's verification fails twice after distinct fix attempts.
  → planning
- **E4** — a step's effort exceeds roughly 3× its apparent scope.
  → planning
- **E5** — a plan checkpoint is reached. → human

Escalation is contract compliance, not failure. The safest autonomous
agent is not the one that never asks questions; it is the one that knows
exactly when it must stop.

**Prohibited actions:**
- **P1** — opportunistic refactoring: improvements outside plan scope.
  Disposition: one line in findings' Out-of-scope observations (or a new
  task), never in this diff.
- **P2** — scope additions, however adjacent.
- **P3** — editing the plan. The implementer proposes; only the Planning
  phase, with human approval, disposes.
- **P4** — marking a step complete without running its named verification.

**Artifact — `ledger.md`:** the deviation ledger. A deviation is any
divergence from the plan's steps, ordering, interfaces, or scope that did
*not* trigger escalation (judged within autonomy boundaries). The Entries
section holds one fenced yaml list; each entry:

```yaml
- step: <plan step>
  what: <what was done differently>
  why: <reason>
  plan_impact: none | <which later steps/criteria are affected>
  status: within-autonomy | escalated-plan | escalated-human | pending-review
```

**An empty ledger (`[]`) is a signed claim, not an absence:** it asserts
"the diff matches the plan exactly," and Review will test that assertion.

**Quality guarantees:**
- G1. Every ledger entry is complete (all five fields).
- G2. Every escalation trigger that fired was actually escalated (Review
  hunts for E2-class changes hiding in the diff).
- G3. All plan verifications executed and passing, or their steps carry
  ledger entries.

**Exit criteria:** every plan step is done (verification passed) or
deferred (ledger entry with plan_impact assessed); acceptance criteria
pass; ledger finalized.

**Backward transitions:** → Planning (E1–E4); → human (E5).
