---
contract: findings
consumes: [request, intent]
produces: findings
gate: null
backward: [intent]
artifact_sections:
  - Scope statement
  - Current state
  - Constraints
  - Assumptions
  - Open questions
  - Out-of-scope observations
telemetry:
  - blocking_questions_count
  - assumptions_unverified_count
---
# Findings Contract

**The contract:** before non-trivial work is planned, the current state of
the world is established as *verifiable facts*, and everything not yet
known is surfaced as an explicit question or assumption — never silently
guessed. Research owns exactly the questions **only the codebase can
answer**; questions only the human can answer belong to the Intent
Contract.

**Inputs:** confirmed `intent.md` (never the raw request directly, though
its hash is pinned for provenance).

**Artifact — `findings.md`:**

- **Scope statement** — one paragraph: what question this research
  answers, restating the confirmed intent in the researcher's own words.
- **Current state** — relevant existing implementations, patterns, and
  tests. Rule: every claim carries a `path:line` or document reference.
  Unreferenced claims are contract violations.
- **Constraints** — architectural, compatibility, and policy constraints
  that bound the solution, each citing its source (AGENTS.md decision,
  code, ADR).
- **Assumptions** — things believed but not verified, each tagged
  `[verified]` (with reference) or `[unverified]`.
- **Open questions** — what research could not determine, each tagged
  `[blocking]` or `[non-blocking]`.
- **Out-of-scope observations** — problems noticed but not part of this
  task; the disposition target for the Execution Contract's refactor ban.

**Consumers:** the Planning contract (primary); the human (the document
that lets work be redirected before any plan exists).

**Quality guarantees:**
- G1. Zero unreferenced factual claims about the codebase.
- G2. Every assumption and open question is tagged.
- G3. The scope statement matches the confirmed intent.

**Blocking conditions / exit criteria:** no `[blocking]` open questions
remain — each is either resolved (moved to Current state with a reference)
or explicitly answered by the human. `[non-blocking]` questions may
survive into the plan's Risks section. No consent gate: exit is
mechanical.

**Backward transitions:** → Intent, when investigation invalidates the
confirmed intent (the task as confirmed is not the task the codebase
permits). Return with the specific contradiction.
