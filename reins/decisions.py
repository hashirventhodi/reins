"""The append-only decision log (M2).

Stores exactly the facts that are NOT derivable from artifacts: gate
consents, bypass, escalations, backward routing, merge, and verifications
(a check ran against a tree and reached a judgment — D17). This module has
no workflow knowledge — it validates record shape on append and reads
tolerantly; interpreting decisions is frontier's job.

Invariants (blueprint §2.4):
  - append-only: the module exposes no delete/rewrite;
  - strict append (malformed decisions are rejected before touching disk),
    tolerant read (corrupted lines are skipped and reported as warnings,
    never a crash);
  - every consent pins the hash of the exact artifact consented to;
    whether a pinned hash still matches is frontier's question, not ours.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import PipelineError
from .schemas import (
    CONTRACTS,
    DECISION_TYPES,
    ESCALATIONS,
    GIT_REF_RE,
    LANES,
    VERDICTS,
    VERIFICATION_VERDICTS,
    VERIFIER_RE,
)

FILENAME = "decisions.jsonl"

_HASH_FIELDS = ("intent_hash", "plan_hash", "request_hash", "review_hash",
                "evidence_hash")
# Fields holding a git object reference rather than a content hash (D16).
_GIT_REF_FIELDS = ("tree_ref",)

# Required payload fields per decision type (beyond 'type' and 'ts').
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "intent_confirmed": ("intent_hash", "edited"),
    "plan_approved": ("plan_hash", "edited"),
    "bypass": ("request_hash", "reason"),
    "escalation": ("trigger_id", "from_contract", "detail"),
    "returned": ("to_contract", "reason"),
    "merged": ("commit",),
    "verification": ("verifier", "tool", "predicate", "verdict", "tree_ref",
                     "evidence_hash", "standard_touched"),
    "disposition": ("lane", "floor"),
}
# Optional payload fields per type (anything else is rejected on append).
OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "intent_confirmed": (),
    "plan_approved": (),
    "bypass": (),
    "escalation": (),
    "returned": ("verdict", "review_hash", "trigger_id"),
    "merged": (),
    "verification": (),
    "disposition": ("override_reason",),
}


class DecisionError(PipelineError):
    """A decision record is malformed (raised on append, never on read)."""


@dataclass(frozen=True)
class Decision:
    type: str
    ts: str                      # ISO-8601 UTC ('...Z'); lexical order == time order
    data: dict

    def __getattr__(self, name: str):
        try:
            return self.data[name]
        except KeyError as exc:  # pragma: no cover - attribute protocol
            raise AttributeError(name) from exc

    def to_dict(self) -> dict:
        return {"type": self.type, "ts": self.ts, **self.data}


@dataclass
class DecisionLog:
    decisions: list[Decision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def of_type(self, dtype: str) -> list[Decision]:
        return [d for d in self.decisions if d.type == dtype]

    def latest(self, dtype: str) -> Decision | None:
        matches = self.of_type(dtype)
        return matches[-1] if matches else None


def _validate(dtype: str, ts: str, data: dict) -> None:
    if dtype not in DECISION_TYPES:
        raise DecisionError(f"unknown decision type {dtype!r}")
    if not isinstance(ts, str) or not ts.endswith("Z"):
        raise DecisionError(f"ts must be ISO-8601 UTC ending in 'Z', got {ts!r}")
    required, optional = REQUIRED_FIELDS[dtype], OPTIONAL_FIELDS[dtype]
    missing = [f for f in required if f not in data]
    extra = [f for f in data if f not in required + optional]
    if missing or extra:
        raise DecisionError(
            f"{dtype}: missing fields {missing or 'none'}, "
            f"unexpected fields {extra or 'none'}")
    for f in _HASH_FIELDS:
        if f in data and not str(data[f]).startswith("sha256:"):
            raise DecisionError(f"{dtype}.{f} must be a 'sha256:' hash")
    for f in _GIT_REF_FIELDS:      # D16: a git object reference, not a hash
        if f in data and not GIT_REF_RE.match(str(data[f])):
            raise DecisionError(
                f"{dtype}.{f} must be a 'git:<object id>' reference "
                f"(40 or 64 hex), got {data[f]!r}")
    if dtype in ("intent_confirmed", "plan_approved") and not isinstance(
            data["edited"], bool):
        raise DecisionError(f"{dtype}.edited must be a boolean")
    if dtype == "verification":
        if not VERIFIER_RE.match(str(data["verifier"])):
            raise DecisionError(
                f"verification.verifier must be a lowercase slug, got "
                f"{data['verifier']!r}")
        if data["verdict"] not in VERIFICATION_VERDICTS:
            raise DecisionError(
                f"verification.verdict {data['verdict']!r} not in "
                f"{list(VERIFICATION_VERDICTS)}")
        if not isinstance(data["standard_touched"], bool):
            raise DecisionError("verification.standard_touched must be a boolean")
        for f in ("tool", "predicate"):
            if not isinstance(data[f], str) or not data[f].strip():
                raise DecisionError(f"verification.{f} must be a non-empty string")
    if dtype == "disposition":
        from .floor import at_or_above     # one definition of the ordering
        for f in ("lane", "floor"):
            if data[f] not in LANES:
                raise DecisionError(
                    f"disposition.{f} {data[f]!r} not in {list(LANES)}")
        reason = data.get("override_reason")
        if not at_or_above(data["lane"], data["floor"]):
            # An escape hatch must exist, or people route around the system
            # entirely — but it must be loud, reasoned, and countable (D20).
            if not isinstance(reason, str) or not reason.strip():
                raise DecisionError(
                    f"disposition.lane {data['lane']!r} is below the computed "
                    f"floor {data['floor']!r}; a below-floor lane requires a "
                    "non-empty override_reason")
        elif reason is not None:
            raise DecisionError(
                "disposition.override_reason is only for a lane below the "
                "computed floor")
    if dtype == "escalation" and data["trigger_id"] not in ESCALATIONS:
        raise DecisionError(
            f"escalation.trigger_id {data['trigger_id']!r} not in "
            f"{sorted(ESCALATIONS)}")
    if dtype == "escalation" and data["from_contract"] not in CONTRACTS:
        raise DecisionError(
            f"escalation.from_contract {data['from_contract']!r} unknown")
    if dtype == "returned" and data["to_contract"] not in CONTRACTS:
        raise DecisionError(f"returned.to_contract {data['to_contract']!r} unknown")
    if dtype == "returned" and "verdict" in data and data["verdict"] not in VERDICTS:
        raise DecisionError(f"returned.verdict {data['verdict']!r} not in {VERDICTS}")


def make(dtype: str, ts: str, **data) -> Decision:
    """Construct a validated Decision (strictness lives here + append)."""
    _validate(dtype, ts, data)
    return Decision(type=dtype, ts=ts, data=data)


def append(task_dir: str | Path, decision: Decision) -> None:
    """Validate and append one record. Append is the only write path."""
    _validate(decision.type, decision.ts, decision.data)
    path = Path(task_dir) / FILENAME
    line = json.dumps(decision.to_dict(), sort_keys=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read(task_dir: str | Path) -> DecisionLog:
    """Tolerant read: skip corrupt/unknown lines with a warning."""
    path = Path(task_dir) / FILENAME
    log = DecisionLog()
    if not path.exists():
        return log
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            dtype, ts = raw.pop("type"), raw.pop("ts")
            _validate(dtype, ts, raw)
        except (json.JSONDecodeError, KeyError, TypeError, DecisionError) as exc:
            log.warnings.append(f"{FILENAME}:{lineno}: skipped ({exc})")
            continue
        log.decisions.append(Decision(type=dtype, ts=ts, data=raw))
    return log
