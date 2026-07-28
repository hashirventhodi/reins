"""Schema registry for pipeline artifacts and contracts.

This module is DATA, not logic. It declares:
  - the artifact types and their required frontmatter fields and sections,
  - which upstream artifacts each type must pin in `consumes[]`,
  - the closed enums (verdicts, ledger statuses, escalation triggers,
    decision types),
  - mechanically checkable section rules (interpreted by validate.py, M1),
  - the telemetry metric registry.

The canonical contract texts in contracts/*.md carry frontmatter declaring
the same facts; tests/test_schema_parity.py asserts the two never drift
(risk R1 in the blueprint). Breaking changes here require a
PIPELINE_VERSION bump.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PIPELINE_VERSION = 1

# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------

VERDICTS = (
    "approve",
    "approve-with-fixes",
    "return-to-implement",
    "return-to-plan",
)

LEDGER_STATUSES = (
    "within-autonomy",
    "escalated-plan",
    "escalated-human",
    "pending-review",
)

# Escalation triggers of the Execution Contract. E1-E4 route to planning,
# E5 routes to the human (checkpoint).
ESCALATIONS = {
    "E1": "plan assumption discovered false",
    "E2": "public interface / persisted data shape / new dependency not in plan",
    "E3": "step verification failed twice after distinct fix attempts",
    "E4": "step effort exceeds ~3x its apparent scope",
    "E5": "plan checkpoint reached",
}
ESCALATION_ROUTES = {"E1": "planning", "E2": "planning", "E3": "planning",
                     "E4": "planning", "E5": "human"}

# Decision record types (decisions.jsonl). Closed enum; see blueprint §2.4.
DECISION_TYPES = (
    "intent_confirmed",   # {intent_hash, edited: bool}
    "plan_approved",      # {plan_hash, edited: bool}
    "bypass",             # {request_hash, reason} — RETIRED (D22): readable
                          # for historical logs, no longer creatable
    "escalation",         # {trigger_id, from_contract, detail}
    "returned",           # {verdict, to_contract, review_hash}
    "merged",             # {commit}
    "verification",       # see VERIFICATION_* below (D17)
    "disposition",        # {lane, floor, override_reason?} (D20)
)

# --- verification records (D17) --------------------------------------------
# A verification is a non-derivable fact — a check ran against a tree and
# reached a judgment — which is why it lives in the decision log beside
# `merged`, not in the artifact chain.
#
# The record is a stable public contract, deliberately not shaped around any
# one checker. Any verifier answers all six questions: which class of check,
# what produced the verdict, what claim was tested, what the judgment was,
# against which tree, and on what evidence.
#
# Outcomes are a closed enum because the vocabulary is universal and small.
# `inconclusive` is not a failure: a scanner that timed out or a benchmark
# too noisy to call must be recordable without asserting either result.
VERIFICATION_VERDICTS = ("pass", "fail", "inconclusive")

# The verifier is an open slug, not an enum: adding a verifier (lint,
# security, performance, migration…) must never require a product change.
# The format check catches garbage; telemetry grouping by verifier surfaces
# typos as a lone class with count 1.
VERIFIER_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# --- process lanes (D18) ---------------------------------------------------
# Ordered least to most process. The product holds this vocabulary because
# enforcing "the chosen lane is at or above the computed floor" needs an
# ordering, and an ordering cannot be enforced over names the product does
# not know. Lane *presets* (which obligations each implies) stay runtime
# policy; only the ordering is product truth.
LANES = ("express", "full")

# Assumption / open-question tags (findings.md).
ASSUMPTION_TAGS = ("[verified]", "[unverified]")
QUESTION_TAGS = ("[blocking]", "[non-blocking]")

# The literal line review.md's Fidelity section must contain.
UNDECLARED_DEVIATIONS_VALUES = ("none", "found")

# ---------------------------------------------------------------------------
# Telemetry metric registry
# ---------------------------------------------------------------------------
# Contracts declare (in frontmatter) which metric IDs justify their
# existence; telemetry.py (M4) implements one function per ID. Task-level
# metrics are emitted for every record regardless of contract.

CONTRACT_TELEMETRY_METRICS = (
    "intent_request_delta",
    "nongoals_count",
    "intent_edited_at_gate",
    "blocking_questions_count",
    "assumptions_unverified_count",
    "plan_edited_at_gate",
    "out_of_scope_count",
    "escalations",
    "ledger_entries",
    "self_corrections",
    "verdict_sequence",
    "undeclared_deviations_found",
)
TASK_TELEMETRY_METRICS = ("pipeline", "task_ref", "duration_by_phase",
                          "verifications", "disposition")
ALL_TELEMETRY_METRICS = CONTRACT_TELEMETRY_METRICS + TASK_TELEMETRY_METRICS

# ---------------------------------------------------------------------------
# Artifact schemas
# ---------------------------------------------------------------------------

# Frontmatter fields common to all produced artifacts (not request.md).
COMMON_FRONTMATTER = ("pipeline", "contract", "task", "produced_at", "consumes")

# Artifact types that exist only as consume targets, never as files under
# the task directory (the review pins the branch head tree hash as "diff").
VIRTUAL_ARTIFACTS = frozenset({"diff"})

# Pinned-reference formats (D16). Two identities, deliberately distinct:
#   sha256:<64 hex>  content-addressed artifacts — the hash of exact file bytes
#   git:<object id>  virtual artifacts — a git object reference (40 hex on
#                    sha1 repos, 64 on sha256 repos)
# A git object id is already a stable identity; re-hashing one to imitate a
# content hash would destroy the distinction and the legibility that D15's
# runtime diff-currency check depends on.
CONTENT_REF_PREFIX = "sha256:"
GIT_REF_PREFIX = "git:"
REF_PREFIXES = (CONTENT_REF_PREFIX, GIT_REF_PREFIX)
# Declared here, not in the modules that check them, so the validator and the
# decision log cannot drift on what a reference looks like.
CONTENT_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_REF_RE = re.compile(r"^git:(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class Schema:
    """Schema for one artifact type."""

    artifact: str                       # artifact type name == filename stem
    produced_by: str | None             # contract name; None for request
    frontmatter_fields: tuple[str, ...]
    consumes_spec: tuple[str, ...]      # upstream artifact types to pin
    required_sections: tuple[str, ...]  # ordered H2 headings
    section_rules: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # A second *accepted* pin set for the same contract (D21). Purely a
    # compatibility mechanism for the validator, which stays file-only and
    # therefore cannot know a task's lane: it accepts either shape, and the
    # frontier — which does read the decision log — decides which shape is
    # legal for the lane in force. Not a second execution path: the same
    # contract produces the artifact either way.
    consumes_alt: tuple[str, ...] | None = None

    @property
    def filename(self) -> str:
        return f"{self.artifact}.md"


SCHEMAS: dict[str, Schema] = {
    "request": Schema(
        artifact="request",
        produced_by=None,
        frontmatter_fields=("task", "source_ref", "created_at"),
        consumes_spec=(),
        required_sections=(),          # body is the verbatim raw request
        section_rules={},
    ),
    "intent": Schema(
        artifact="intent",
        produced_by="intent",
        frontmatter_fields=COMMON_FRONTMATTER,
        consumes_spec=("request",),
        required_sections=(
            "Problem statement",
            "Goals",
            "Success criteria",
            "Non-goals",
            "Scope of intent",
        ),
        section_rules={"Non-goals": ("nonempty",)},
    ),
    "findings": Schema(
        artifact="findings",
        produced_by="findings",
        frontmatter_fields=COMMON_FRONTMATTER,
        consumes_spec=("request", "intent"),
        required_sections=(
            "Scope statement",
            "Current state",
            "Constraints",
            "Assumptions",
            "Open questions",
            "Out-of-scope observations",
        ),
        section_rules={
            "Current state": ("referenced-claims",),
            "Assumptions": ("tagged-assumptions",),
            "Open questions": ("tagged-questions",),
        },
    ),
    "plan": Schema(
        artifact="plan",
        produced_by="planning",
        frontmatter_fields=COMMON_FRONTMATTER,
        consumes_spec=("intent", "findings"),
        required_sections=(
            "Objective & acceptance criteria",
            "Steps",
            "Test strategy",
            "Reversibility",
            "Risks",
            "Out of scope",
            "Checkpoints",
        ),
        section_rules={
            "Steps": ("verify-lines",),
            "Out of scope": ("nonempty",),
        },
    ),
    "ledger": Schema(
        artifact="ledger",
        produced_by="execution",
        frontmatter_fields=COMMON_FRONTMATTER,
        consumes_spec=("plan",),
        consumes_alt=("request",),      # express: no plan exists (D21)
        required_sections=("Entries",),
        section_rules={"Entries": ("ledger-entries",)},
    ),
    "review": Schema(
        artifact="review",
        produced_by="review",
        frontmatter_fields=COMMON_FRONTMATTER,
        consumes_spec=("intent", "plan", "ledger", "diff"),
        # express: the immutable request is the standard adjudicated against
        # in place of a confirmed intent and an approved plan (D21)
        consumes_alt=("request", "ledger", "diff"),
        required_sections=("Fidelity", "Findings", "Coverage", "Verdict"),
        section_rules={
            "Fidelity": ("undeclared-deviations-line",),
            "Coverage": ("nonempty",),
            "Verdict": ("verdict-enum", "verdict-fidelity-consistency"),
        },
    ),
}

# Chain order: the workflow's artifact spine, upstream -> downstream.
CHAIN: tuple[str, ...] = ("request", "intent", "findings", "plan", "ledger", "review")

# Which artifacts a lane requires (D21). One chain per lane, walked by the
# same frontier code — the lane parameterises the walk, it does not fork it.
# `express` keeps the always-on obligations: the work is disclosed (an empty
# ledger is still a signed claim, here that the diff matches the request) and
# independently adjudicated. Only the two consent gates are substituted away,
# since intent.md and plan.md never exist, so gates 1 and 2 cannot fire.
LANE_CHAINS: dict[str, tuple[str, ...]] = {
    "express": ("request", "ledger", "review"),
    "full": CHAIN,
}

# Contract name -> artifact type it produces.
CONTRACT_PRODUCES: dict[str, str] = {
    s.produced_by: s.artifact for s in SCHEMAS.values() if s.produced_by
}

# Contract gates: consent decision required before the workflow proceeds
# past the produced artifact. Review's gate is the merge itself (git-side).
CONTRACT_GATES: dict[str, str | None] = {
    "intent": "intent_confirmed",
    "findings": None,
    "planning": "plan_approved",
    "execution": None,
    "review": None,
}

# Legal backward-transition targets per contract.
CONTRACT_BACKWARD: dict[str, tuple[str, ...]] = {
    "intent": (),
    "findings": ("intent",),
    "planning": ("findings",),
    "execution": ("planning",),
    "review": ("execution", "planning"),
}

# Telemetry metric IDs each contract pre-registered as its evidence.
CONTRACT_TELEMETRY: dict[str, tuple[str, ...]] = {
    "intent": ("intent_request_delta", "nongoals_count", "intent_edited_at_gate"),
    "findings": ("blocking_questions_count", "assumptions_unverified_count"),
    "planning": ("plan_edited_at_gate", "out_of_scope_count"),
    "execution": ("escalations", "ledger_entries", "self_corrections"),
    "review": ("verdict_sequence", "undeclared_deviations_found"),
}

CONTRACTS: tuple[str, ...] = tuple(CONTRACT_PRODUCES)


def _check_registry(
    schemas: dict[str, Schema] | None = None,
    chain: tuple[str, ...] | None = None,
) -> None:
    """Structural invariants of the architecture itself, verified before

    any validator logic runs (import-time; parameterized for tests):
      1. exactly one producer for every produced artifact
      2. every consumes edge references a known artifact (or virtual)
      3. exactly one root (request: no producer, consumes nothing)
      4. exactly one terminal (review: consumed by no artifact)
      5. every artifact reachable from the root via consumed-by edges
      6. the consumes graph is acyclic
      7. contract maps are total and mutually consistent
    """
    from .errors import SchemaError

    schemas = SCHEMAS if schemas is None else schemas
    chain = CHAIN if chain is None else chain

    for name, schema in schemas.items():
        if name != schema.artifact:
            raise SchemaError(f"schema key {name!r} != artifact {schema.artifact!r}")
        for consumed in schema.consumes_spec + (schema.consumes_alt or ()):
            if consumed not in schemas and consumed not in VIRTUAL_ARTIFACTS:
                raise SchemaError(f"{name} consumes unknown artifact {consumed!r}")
        for section in schema.section_rules:
            if section not in schema.required_sections:
                raise SchemaError(f"{name}: rule on unknown section {section!r}")

    # 1. exactly one producer per produced artifact
    produced = [s.produced_by for s in schemas.values() if s.produced_by]
    if len(produced) != len(set(produced)):
        raise SchemaError("a contract produces more than one artifact type")

    # 3. exactly one root
    roots = {n for n, s in schemas.items() if s.produced_by is None}
    if roots != {"request"}:
        raise SchemaError(f"expected exactly one root 'request', got {sorted(roots)}")
    if schemas["request"].consumes_spec:
        raise SchemaError("the root artifact must consume nothing")

    # 4. exactly one terminal; 5. reachability from root
    consumed_by: dict[str, set[str]] = {n: set() for n in schemas}
    for name, schema in schemas.items():
        for upstream in schema.consumes_spec:
            if upstream in schemas:
                consumed_by[upstream].add(name)
    terminals = {n for n, downstream in consumed_by.items() if not downstream}
    if terminals != {"review"}:
        raise SchemaError(f"expected exactly one terminal 'review', got {sorted(terminals)}")
    reachable: set[str] = set()
    frontier = ["request"]
    while frontier:
        node = frontier.pop()
        if node in reachable:
            continue
        reachable.add(node)
        frontier.extend(consumed_by[node])
    orphans = set(schemas) - reachable
    if orphans:
        raise SchemaError(f"artifacts unreachable from root: {sorted(orphans)}")

    # 6. acyclicity (general DFS, independent of CHAIN ordering)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in schemas}

    def dfs(node: str) -> None:
        color[node] = GREY
        for upstream in schemas[node].consumes_spec:
            if upstream not in schemas:
                continue
            if color[upstream] == GREY:
                raise SchemaError(f"consumes cycle through {upstream!r}")
            if color[upstream] == WHITE:
                dfs(upstream)
        color[node] = BLACK

    for n in schemas:
        if color[n] == WHITE:
            dfs(n)

    # 7. contract maps total and consistent (only for the real registry —
    # parameterized negative tests exercise the graph rules above)
    if schemas is SCHEMAS:
        for mapping in (CONTRACT_GATES, CONTRACT_BACKWARD, CONTRACT_TELEMETRY):
            if set(mapping) != set(CONTRACT_PRODUCES):
                raise SchemaError("contract maps out of sync with CONTRACT_PRODUCES")
        for contract, targets in CONTRACT_BACKWARD.items():
            for t in targets:
                if t not in CONTRACT_PRODUCES:
                    raise SchemaError(f"{contract}: backward target {t!r} not a contract")
        for contract, metrics in CONTRACT_TELEMETRY.items():
            for m in metrics:
                if m not in CONTRACT_TELEMETRY_METRICS:
                    raise SchemaError(f"{contract}: unknown telemetry metric {m!r}")
        if set(chain) != set(schemas):
            raise SchemaError("CHAIN must enumerate exactly the artifact types")
        order = {name: i for i, name in enumerate(chain)}
        for schema in schemas.values():
            for upstream in schema.consumes_spec + (schema.consumes_alt or ()):
                if upstream in schemas and order[upstream] >= order[schema.artifact]:
                    raise SchemaError(
                        f"{schema.artifact} consumes downstream artifact {upstream!r}"
                    )
        # 8. every lane chain is a prefix-closed subsequence of CHAIN whose
        #    artifacts can actually pin what they need in that lane (D21).
        for lane, lane_chain in LANE_CHAINS.items():
            if lane not in LANES:
                raise SchemaError(f"LANE_CHAINS has unknown lane {lane!r}")
            if lane_chain[0] != "request":
                raise SchemaError(f"lane {lane!r} must start at the root")
            if lane_chain[-1] != "review":
                raise SchemaError(f"lane {lane!r} must end at the terminal")
            if list(lane_chain) != [a for a in chain if a in set(lane_chain)]:
                raise SchemaError(f"lane {lane!r} chain is not in CHAIN order")
            present = set(lane_chain)
            for atype in lane_chain:
                if atype == "request":
                    continue
                spec, alt = schemas[atype].consumes_spec, schemas[atype].consumes_alt
                options = [spec] + ([alt] if alt else [])
                if not any(set(o) - VIRTUAL_ARTIFACTS <= present for o in options):
                    raise SchemaError(
                        f"lane {lane!r}: {atype} cannot pin its inputs "
                        f"(needs one of {options} within {sorted(present)})")
        if set(LANE_CHAINS) != set(LANES):
            raise SchemaError("every lane needs a chain")


_check_registry()
