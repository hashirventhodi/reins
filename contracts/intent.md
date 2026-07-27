---
contract: intent
consumes: [request]
produces: intent
gate: intent_confirmed
backward: []
bypass: false          # retired (D22); the entry gate is the computed floor
artifact_sections:
  - Problem statement
  - Goals
  - Success criteria
  - Non-goals
  - Scope of intent
telemetry:
  - intent_request_delta
  - nongoals_count
  - intent_edited_at_gate
---
# Intent Contract

**The contract:** before any investigation or planning, an unstructured
human request is transformed into a normalized statement of intent, and
that statement is confirmed by the human. Refine is intent normalization,
not investigation: it owns exactly the questions **only the human can
answer** — what problem, for whom, what success looks like, what is
explicitly out. Questions only the codebase can answer belong to Research.

**Inputs:** `request.md` — the immutable, verbatim raw request. This
contract never modifies its input; the request/intent pair is what makes
`intent_request_delta` computable forever.

**Dispatch (the entry gate no longer lives here):** this contract once
carried a typed early return, `Refine(request) -> intent.md | bypass`,
classifying sub-threshold work out of the pipeline entirely. That was the
wrong shape twice over: the classification was prose judged by the agent
that benefits from judging it low, and its cheap branch discarded
independent adjudication — the guarantee whose value tracks blast radius,
not effort — in order to avoid the two consent gates, which are what
actually cost human attention.

The threshold is now computed, not judged: a floor derived mechanically
from the change and repo policy, and a human-disposed lane at or above it
(D18/D20). Sub-threshold work runs the **express** lane, where this
contract simply does not run — `request.md` itself is the standard Review
adjudicates against — while disclosure, adjudication, and verification
remain in force (D21). Nothing exits the pipeline unreviewed.

When this contract *is* invoked, the work is pipeline-bound and receives
full elicitation.

**Artifact — `intent.md`:** contains only information that cannot be
derived from the codebase.

- **Problem statement** — the problem, not the requested solution. If the
  request is solution-shaped, this section states the underlying problem
  the solution implies, confirmed with the human.
- **Goals** — what the change should accomplish, from the human's view.
- **Success criteria** — how the human will judge that intent was served.
  These are validation criteria (does it serve the intent), distinct from
  the plan's acceptance criteria (does it meet the spec); Review
  adjudicates against both.
- **Non-goals** — explicitly excluded outcomes. May not be empty: non-goals
  are the thing humans never volunteer and always have.
- **Scope of intent** — the boundary of what the human is asking for, in
  their terms (not files or modules — that is Research's vocabulary).

**Quality guarantees:**
- G1. Every statement is intent (human-sourced), never investigation
  (codebase-sourced).
- G2. Solution-shaped requests are re-expressed as problems before goals
  are written.
- G3. Non-goals is nonempty.

**Blocking conditions:** the human is unavailable to answer an intent
question that materially forks the goals — stop rather than guess.

**Exit criteria:** explicit human confirmation of `intent.md` ("yes, that
is what I meant") — consent gate 1 of 3. Confirmation is recorded with the
hash of the confirmed file; any later edit voids it and reopens the gate.
Human edits at this gate are the contract *working*, not failing.

**Backward transitions:** none (source phase). Research returns here when
investigation invalidates the confirmed intent.
