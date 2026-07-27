"""Frontier (M2): derive task status and the next contract.

A pure, deterministic function of (artifact bytes, decisions.jsonl):
identical inputs yield a byte-for-byte identical Frontier (no wall time,
no filesystem ordering, no absolute paths — the task is identified by its
directory *name*). This determinism is what makes /work safely resumable
and lets any runtime rely on identical behavior.

Status is computed, never stored. The only stored state the frontier
consults besides artifacts is the decision log — the facts that genuinely
are not derivable (consents, bypass, escalations, routing, merge).

Normative precedence (first match wins):
  1. INVALID    — any artifact invalid or task-level violations
  2. BYPASSED   — valid bypass decision (terminal)
  3. DONE       — merged decision (terminal)
  4. STALE      — any stale artifact; next = producer of first stale
  5. BLOCKED    — unresolved escalation (no later 'returned' decision)
  6. RETURNED   — pending backward routing: a 'returned' decision not yet
                  superseded by regeneration of its target, or a fresh
                  review whose verdict is return-to-*
  7. AWAITING_INTENT_CONSENT / AWAITING_PLAN_APPROVAL — gate artifact
     exists fresh but carries no currently-valid consent (consent is
     hash-pinned; editing the artifact voids it)
  8. chain walk — first missing artifact names the phase:
     intent->NEW/REFINING, findings->RESEARCHING, plan->PLANNING,
     ledger->IMPLEMENTING, review->REVIEWING
     (NEW iff nothing but the request exists and the log is empty)
  9. UNVERIFIED — chain complete and approved, but no passing verification
     covers the reviewed tree (D19). Not a human stop: the runtime can
     resolve it by running the checks and recording them.
 10. AWAITING_MERGE — full fresh chain, approving verdict, verified,
     not merged
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import artifact as art
from . import decisions as dec
from . import validate as val
from .schemas import CHAIN, CONTRACT_PRODUCES, LANE_CHAINS, SCHEMAS

STATUSES = (
    "INVALID", "BYPASSED", "DONE", "STALE", "BLOCKED", "RETURNED",
    "AWAITING_INTENT_CONSENT", "AWAITING_PLAN_APPROVAL",
    "NEW", "REFINING", "RESEARCHING", "PLANNING", "IMPLEMENTING",
    "REVIEWING", "UNVERIFIED", "AWAITING_MERGE",
)

# Statuses where the orchestrator must STOP for a human.
HUMAN_STATUSES = frozenset({
    "AWAITING_INTENT_CONSENT", "AWAITING_PLAN_APPROVAL", "BLOCKED",
    "AWAITING_MERGE",
})
TERMINAL_STATUSES = frozenset({"BYPASSED", "DONE"})

_PRODUCER = {atype: contract for contract, atype in CONTRACT_PRODUCES.items()}
_PHASE_FOR_MISSING = {
    "intent": "REFINING", "findings": "RESEARCHING", "plan": "PLANNING",
    "ledger": "IMPLEMENTING", "review": "REVIEWING",
}


@dataclass(frozen=True)
class Frontier:
    task: str                      # directory NAME (never an absolute path)
    status: str
    next_contract: str | None
    reason: str
    detail: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "status": self.status,
            "next_contract": self.next_contract,
            "reason": self.reason,
            "detail": self.detail,
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def _produced_at(task_dir: Path, atype: str) -> str | None:
    """Return produced_at in the canonical decision-ts shape ('...THH:MM:SSZ').

    D26 (fixed, mechanism amended by D30): PyYAML's implicit resolver
    auto-parsed produced_at into a datetime whose str() formatted as
    '... HH:MM:SS+00:00' (space, offset), not the decision log's
    '...THH:MM:SSZ'. The space byte sorts before 'T', so the RETURNED
    clearing comparison below concluded a same-day regeneration had NOT
    happened, regardless of actual chronology. miniyaml keeps timestamps
    as plain strings, which removes the bug class for artifacts written
    from now on — but artifacts re-serialized by the old PyYAML path may
    literally contain the space-separated form, so string values are
    still normalized here (the sole call site). D11's rule, the decision
    log's format and the artifact schema stay untouched."""
    path = task_dir / SCHEMAS[atype].filename
    if not path.exists():
        return None
    try:
        value = art.load(path).frontmatter.get("produced_at")
    except Exception:  # invalid artifacts are handled by precedence 1
        return None
    if value is None:
        return None
    if isinstance(value, _dt.datetime):  # unreachable via miniyaml; kept
        if value.tzinfo is None:         # for callers passing artifacts
            value = value.replace(tzinfo=_dt.timezone.utc)   # loaded elsewhere
        return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _valid_consent(task_dir: Path, log: dec.DecisionLog, dtype: str,
                   atype: str, hash_field: str) -> bool:
    """Latest consent of dtype counts iff its pinned hash matches the

    current file bytes. Editing after consent voids it (re-consent
    required) — D3."""
    latest = log.latest(dtype)
    if latest is None:
        return False
    path = task_dir / SCHEMAS[atype].filename
    if not path.exists():
        return False
    return latest.data.get(hash_field) == art.sha256(path)


def frontier(task_dir: str | Path) -> Frontier:
    d = Path(task_dir)
    task = d.name
    report = val.validate_task(d)
    log = dec.read(d)
    warnings = tuple(log.warnings)

    # The lane in force. Absent disposition means `full` — the pre-D20
    # behaviour, so nothing about an undisposed task changes. A lane is only
    # ever a choice about *which* artifacts a task needs; the contracts that
    # produce them, and the obligations that are always on (disclosure,
    # adjudication, verification), are identical either way.
    disposition = log.latest("disposition")
    lane = disposition.data["lane"] if disposition else "full"
    required = LANE_CHAINS.get(lane, CHAIN)

    def F(status: str, next_contract: str | None, reason: str,
          **detail) -> Frontier:
        return Frontier(task, status, next_contract, reason,
                        dict(sorted(detail.items())), warnings)

    # 1. INVALID
    invalid = [a for a in CHAIN if report.artifacts[a].status == val.INVALID]
    if invalid or report.task_violations:
        rules = sorted({v.rule for v in report.all_violations()
                        if v.rule != "stale"})
        return F("INVALID", None,
                 f"fix violations before any contract runs: {', '.join(rules)}",
                 artifacts=invalid,
                 violations=[v.to_dict() for v in report.all_violations()])

    # 2. BYPASSED
    bypass = log.latest("bypass")
    if bypass is not None:
        req = d / SCHEMAS["request"].filename
        if req.exists() and bypass.data.get("request_hash") == art.sha256(req):
            return F("BYPASSED", None,
                     f"below pipeline threshold: {bypass.data['reason']}")

    # 3. DONE
    merged = log.latest("merged")
    if merged is not None:
        return F("DONE", None, f"merged as {merged.data['commit']}")

    # 4. STALE
    stale = [a for a in CHAIN if report.artifacts[a].status == val.STALE]
    if stale:
        first = stale[0]
        producer = _PRODUCER[first]
        return F("STALE", producer,
                 f"{SCHEMAS[first].filename} is stale; re-run the "
                 f"{producer} contract (re-entry)",
                 first_stale=first, stale=stale)

    # 5. BLOCKED — an escalation with no later 'returned' routing
    pending_esc = None
    for entry in log.decisions:
        if entry.type == "escalation":
            pending_esc = entry
        elif entry.type == "returned":
            pending_esc = None
    if pending_esc is not None:
        return F("BLOCKED", None,
                 f"escalation {pending_esc.data['trigger_id']} from "
                 f"{pending_esc.data['from_contract']}: "
                 f"{pending_esc.data['detail']} — human routing required",
                 trigger=pending_esc.data["trigger_id"],
                 from_contract=pending_esc.data["from_contract"])

    # 6. RETURNED — pending decision-based routing…
    routed = log.latest("returned")
    if routed is not None:
        target = routed.data["to_contract"]
        target_artifact = CONTRACT_PRODUCES[target]
        produced = _produced_at(d, target_artifact)
        if produced is None or produced <= routed.ts:
            return F("RETURNED", target,
                     f"routed back to {target}: {routed.data['reason']}",
                     to=target)
    # …or a fresh review whose verdict routes backward
    review_path = d / SCHEMAS["review"].filename
    if report.artifacts["review"].status == val.FRESH:
        verdict = art.load(review_path).sections["Verdict"].strip()
        if verdict == "return-to-implement":
            return F("RETURNED", "execution",
                     "review verdict return-to-implement", to="execution",
                     verdict=verdict)
        if verdict == "return-to-plan":
            return F("RETURNED", "planning",
                     "review verdict return-to-plan", to="planning",
                     verdict=verdict)

    # 7. Gates (hash-pinned consent; D3)
    if report.artifacts["intent"].status == val.FRESH and not _valid_consent(
            d, log, "intent_confirmed", "intent", "intent_hash"):
        return F("AWAITING_INTENT_CONSENT", None,
                 "intent.md awaits human confirmation (gate 1 of 3); "
                 "edits void prior confirmation")
    if report.artifacts["plan"].status == val.FRESH and not _valid_consent(
            d, log, "plan_approved", "plan", "plan_hash"):
        return F("AWAITING_PLAN_APPROVAL", None,
                 "plan.md awaits human approval (gate 2 of 3); "
                 "edits void prior approval")

    # 8. Chain walk — over the lane's required artifacts (D21). The lane
    #    parameterises this walk; it does not fork it. A task with no
    #    disposition is `full`, which is CHAIN, so behaviour is unchanged.
    for atype in required:
        if report.artifacts[atype].status == val.MISSING:
            if atype == "request":
                return F("INVALID", None, "task has no request.md",
                         artifacts=["request"])
            phase = _PHASE_FOR_MISSING[atype]
            pristine = (atype == "intent" and not log.decisions
                        and all(report.artifacts[a].status == val.MISSING
                                for a in CHAIN if a != "request"))
            status = "NEW" if pristine else phase
            producer = _PRODUCER[atype]
            return F(status, producer,
                     f"next: produce {SCHEMAS[atype].filename} via the "
                     f"{producer} contract")

    # 9. UNVERIFIED — chain complete and approved, but no passing check
    #    covers the tree that was reviewed (D19).
    reviewed_tree = art.consumed_hashes(art.load(review_path)).get("diff")
    latest_by_verifier: dict[str, dec.Decision] = {}
    for entry in log.decisions:
        if (entry.type == "verification"
                and entry.data.get("tree_ref") == reviewed_tree):
            latest_by_verifier[entry.data["verifier"]] = entry
    not_passing = sorted(name for name, entry in latest_by_verifier.items()
                         if entry.data["verdict"] != "pass")
    if not latest_by_verifier:
        return F("UNVERIFIED", None,
                 f"no verification covers the reviewed tree {reviewed_tree}; "
                 "run the plan's verifications and record them with "
                 "`pipeline verify`",
                 reviewed_tree=reviewed_tree)
    if not_passing:
        return F("UNVERIFIED", None,
                 "latest verification did not pass for: "
                 f"{', '.join(not_passing)}",
                 reviewed_tree=reviewed_tree, not_passing=not_passing)

    # 10. AWAITING_MERGE
    verdict = art.load(review_path).sections["Verdict"].strip()
    return F("AWAITING_MERGE", None,
             f"review verdict {verdict}; merge (gate 3 of 3) belongs to "
             "the human and git", verdict=verdict,
             verifiers=sorted(latest_by_verifier))
