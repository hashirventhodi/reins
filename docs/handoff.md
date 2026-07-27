# Architecture Phase Handoff

This document formally closes the architecture phase and opens the
operational phase. It is the charter future contributors and agent
sessions inherit; nothing essential about how to evolve this system
lives outside the repository.

> **Snapshot, not current state.** The figures below were true when the
> architecture phase closed and are left as written — this document is a
> charter, and rewriting its numbers would erase what was actually
> handed over. For current state see README.md and
> docs/implementation-decisions.md; the operational phase has since
> produced D14–D34, including the repackaging that removed the installed
> CLI (D30) and named the project Reins (D32).

## Final state (at handoff)

- 199 passing tests; every documented guarantee is test-backed
- 15 recorded decisions (+1 amendment) in
  docs/implementation-decisions.md; the blueprint holds D1-D9
- Governance ladder in force (docs/governance.md)
- Five contracts (contracts/), one runtime binding (runtime/claude/)
- Deterministic projections: validate, frontier, telemetry, followups
- Every remaining trust boundary explicitly documented
  (D7 consent authenticity, D15 diff currency, guard fail-open)
- No known architectural inconsistencies

## Architecture status

Stable, not immutable. Future changes are driven by operational
evidence, through the governance ladder. Governing principles:

- Deterministic derivation belongs in the product.
- Orchestration belongs in the runtime.
- Human approval remains explicit.
- The runtime must never derive product state.
- New capabilities reuse existing precedents before introducing new
  principles (the decision log is case law).
- Architectural changes climb the governance ladder.

## The operational phase

The goal is not to redesign the architecture; it is to validate it
through daily development. Focus: developer experience, slash commands,
hooks, agent behavior, prompt quality, local-first workflow, speed,
friction reduction, real telemetry.

Evidence sources:
1. **Telemetry** — what the system measures deterministically
   (docs/queries.md runs the quarterly review).
2. **Friction log** — every awkward moment, every bypass, every
   workaround. Friction is product feedback, not user error. Only
   recurring patterns get promoted into architectural change.

## Success criteria

No longer architectural elegance. Measured by whether real software
development improves: does planning improve; does review quality
improve; are follow-up candidates useful; are contracts worth their
cost; which gates create value; where does friction outweigh benefit.

## Final instruction

Do not redesign the architecture unless real usage demonstrates a
consistent need. Prefer small, evidence-backed improvements. Protect
the ownership boundaries and deterministic guarantees unless compelling
operational data justifies changing them.

The architecture has earned the opportunity to prove itself.
The next milestone is not another decision record.
The next milestone is real work.
