# Governance — stable, not immutable

The architecture is stable, not frozen. We evolve it when there is a
clear improvement or when real usage demonstrates a better design.
Telemetry is an important input, not the only permitted one. The goal is
to avoid unnecessary churn, not to avoid change.

Core principles that any change must preserve:
- the product stays deterministic;
- the runtime orchestrates, never decides;
- ownership boundaries stay clear (D9);
- prefer extending existing abstractions over introducing new ones;
- evolve deliberately, with a reason that can be written down.

## The change ladder

**Tier 0 — just do it.** Docs, runtime commands/prompts, queries.
Reversible; zero product bytes. Normal review applies, nothing more.

**Tier 1 — design note + D-entry.** Additive, backward-compatible
product changes: a new optional frontmatter field, a new telemetry
metric function, a new validator rule (with its mandatory passing and
failing fixtures). PIPELINE_VERSION bump only if breaking.

**Tier 2 — a written case.** Contracts, artifact schemas, approval
gates, frontier statuses, the decision enum. The case must pass the
admission test (produced artifact, named downstream consumer,
contestable choice, pre-registered kill criterion) AND cite at least one
grounding instance:
- a telemetry signal, or
- a reproducible failure, or
- one concrete real task where the current design demonstrably got in
  the way.

A Tier-2 change grounded in argument alone is admissible only if it is
cleanly reversible and ships with its kill criterion pre-registered.

**Anti-churn:** Tier-2 changes batch into version bumps and never land
mid-task. A proposal rejected on merits records why, so it isn't
re-litigated without new grounding.

Historical note: v1.0.0 was tagged under a stricter policy ("frozen:
changes require telemetry") whose purpose — preventing taste-driven
churn from the same minds that designed the system — this ladder
preserves in proportionate form. The tag annotation reflects policy at
tag time and stands as history.
