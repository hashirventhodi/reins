---
contract: planning
consumes: [intent, findings]
produces: plan
gate: plan_approved
backward: [findings]
artifact_sections:
  - Objective & acceptance criteria
  - Steps
  - Test strategy
  - Reversibility
  - Risks
  - Out of scope
  - Checkpoints
telemetry:
  - plan_edited_at_gate
  - out_of_scope_count
---
# Planning Contract

**The contract:** work proceeds only against a step-ordered, verifiable,
human-approved plan with explicit boundaries. The plan is the governing
document for both Execution and Review; after approval it can be changed
only by re-entering this phase.

**Inputs:** confirmed `intent.md` and `findings.md` meeting its exit
criteria.

**Artifact — `plan.md`:**

- **Objective & acceptance criteria** — what done means. Each criterion is
  testable — a command, a test name, or an observable behavior. "Works
  correctly" is a violation. Acceptance criteria must trace to the
  intent's success criteria.
- **Steps** — dependency-ordered implementation steps. Each step block
  carries a `verify:` line naming its verification method (test to
  write/run, command to execute, behavior to check).
- **Test strategy** — what gets new tests, what relies on existing
  coverage, and what is consciously untested. The consciously-untested
  list may not be empty by omission — write "none" deliberately.
- **Reversibility** — how this change is rolled back or feature-gated;
  which steps are irreversible. Irreversible steps must be marked — they
  become mandatory human checkpoints.
- **Risks** — carried from findings plus planning-discovered, each with a
  mitigation or an explicit acceptance. Every `[unverified]` assumption
  from findings must appear here or be resolved.
- **Out of scope** — what this plan deliberately does not do. May not be
  empty: an empty section means scoping wasn't decided, only defaulted.
- **Checkpoints** — points during execution requiring human confirmation;
  irreversible steps at minimum.

**Consumers:** Execution (as governing document), Review (as the standard
the diff is adjudicated against), the human (as the approval surface).

**Quality guarantees:**
- G1. Every blocking finding and unverified assumption from findings.md is
  addressed — resolved, mitigated, or accepted in Risks; nothing silently
  dropped.
- G2. Every step has a verification method.
- G3. Every acceptance criterion is testable as written and traceable to
  intent.
- G4. Out of scope is non-empty; Reversibility is answered.

**Blocking conditions:** findings exposes unknowns that make step ordering
a guess — return to Findings with the specific questions rather than
planning around ignorance.

**Exit criteria:** explicit human approval — consent gate 2 of 3, and the
highest-leverage minutes in the workflow. Approval is recorded with the
hash of the approved file; any later edit voids it and reopens the gate.
Approval freezes the plan: the implementer has no write access to its
meaning.

**Backward transitions:** → Findings.
