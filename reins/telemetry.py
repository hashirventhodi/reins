"""Telemetry extraction (M4).

Answers exactly one question: "given a completed task, what metrics can
be deterministically derived?" It never infers quality, never recommends,
never interprets. Extraction is a pure projection from (artifacts,
decisions, contract metadata); append is idempotent.

Self-describing governance, implemented literally (blueprint §10): the
record's metric set is generated from `schemas.CONTRACT_TELEMETRY` — the
same IDs the contract texts declare in their `telemetry:` frontmatter
(parity-tested in test_schema_parity). One metric function per ID lives
in METRICS; a declared ID without a function fails the registry test, so
adding or retiring a contract automatically adds or retires its fields.

Invariants:
  - extraction is read-only over the task directory;
  - a metric that cannot be computed emits None — it never blocks;
  - a phase duration can never be negative (nothing finishes before it
    starts); one that computes negative is invalid, not small — it emits
    None and a warning rather than an impossible measurement (D27);
  - append is idempotent: the key is (task, outcome); re-running extract
    against the same merge never produces a second record;
  - records contain no wall-clock values — extraction of the same task
    bytes yields byte-identical records (golden-testable).
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import re
import warnings as _warnings
from pathlib import Path

from . import artifact as art
from . import decisions as dec
from .errors import PipelineError
from .schemas import (
    ALL_TELEMETRY_METRICS,
    CONTRACT_TELEMETRY,
    PIPELINE_VERSION,
    SCHEMAS,
    TASK_TELEMETRY_METRICS,
)

DEFAULT_PATH = "telemetry.jsonl"


class ExtractionError(PipelineError):
    """The task is not in an extractable state (not DONE or BYPASSED)."""


# --------------------------------------------------------------------------
# Context: everything metric functions may look at (loaded once, read-only)
# --------------------------------------------------------------------------

class _Ctx:
    def __init__(self, task_dir: Path):
        self.dir = task_dir
        self.log = dec.read(task_dir)
        self.artifacts: dict[str, art.Artifact | None] = {}
        for atype in SCHEMAS:
            path = task_dir / SCHEMAS[atype].filename
            try:
                self.artifacts[atype] = art.load(path) if path.exists() else None
            except Exception:
                self.artifacts[atype] = None

    def section(self, atype: str, name: str) -> str | None:
        a = self.artifacts.get(atype)
        if a is None or name not in a.sections:
            return None
        return a.sections[name]

    def fm(self, atype: str, key: str):
        a = self.artifacts.get(atype)
        return None if a is None else a.frontmatter.get(key)


def _bullets(content: str | None) -> list[str]:
    if content is None:
        return []
    from .validate import _bullet_blocks
    return _bullet_blocks(content)


def _body(a: art.Artifact | None) -> str | None:
    return None if a is None else art.body_text(a)


def _parse_ts(value) -> _dt.datetime | None:
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


def _seconds(start, end, *, label: str = "duration") -> int | None:
    a, b = _parse_ts(start), _parse_ts(end)
    if a is None or b is None:
        return None
    delta = int((b - a).total_seconds())
    if delta < 0:
        _warnings.warn(
            f"{label}: computed a negative duration ({delta}s) between "
            f"{a.isoformat()} and {b.isoformat()} — recording None instead "
            "of an impossible measurement (D27)",
            stacklevel=2,
        )
        return None
    return delta


# --------------------------------------------------------------------------
# Metric functions — one per declared ID, all pure, all None-safe
# --------------------------------------------------------------------------

def _intent_request_delta(c: _Ctx):
    req, intent = _body(c.artifacts["request"]), _body(c.artifacts["intent"])
    if req is None or intent is None:
        return None
    ratio = difflib.SequenceMatcher(a=req, b=intent, autojunk=False).ratio()
    return round(1.0 - ratio, 4)


def _nongoals_count(c: _Ctx):
    s = c.section("intent", "Non-goals")
    return None if s is None else len(_bullets(s))


def _gate_edited(c: _Ctx, dtype: str):
    latest = c.log.latest(dtype)
    return None if latest is None else bool(latest.data.get("edited"))


def _blocking_questions_count(c: _Ctx):
    s = c.section("findings", "Open questions")
    if s is None:
        return None
    return sum(1 for b in _bullets(s) if b.startswith("- [blocking]"))


def _assumptions_unverified_count(c: _Ctx):
    s = c.section("findings", "Assumptions")
    if s is None:
        return None
    return sum(1 for b in _bullets(s) if b.startswith("- [unverified]"))


def _out_of_scope_count(c: _Ctx):
    s = c.section("plan", "Out of scope")
    return None if s is None else len(_bullets(s))


def _escalations(c: _Ctx):
    return [{"trigger_id": d.data["trigger_id"],
             "from_contract": d.data["from_contract"]}
            for d in c.log.of_type("escalation")]


def _ledger_entries(c: _Ctx):
    a = c.artifacts["ledger"]
    if a is None:
        return None
    try:
        entries = art.ledger_entries(a)
    except Exception:
        return None
    by_status: dict[str, int] = {}
    for e in entries:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    return {"count": len(entries), "by_status": dict(sorted(by_status.items()))}


def _self_corrections(c: _Ctx):
    # Not derivable yet: orchestrator-side counts have no recording
    # mechanism in the v1 decision enum (see D13). None, never a guess.
    return None


def _verdict_sequence(c: _Ctx):
    seq = [d.data["verdict"] for d in c.log.of_type("returned")
           if "verdict" in d.data]
    current = c.section("review", "Verdict")
    if current is not None and current.strip():
        seq.append(current.strip())
    return seq


def _undeclared_deviations_found(c: _Ctx):
    s = c.section("review", "Fidelity")
    if s is None:
        return None
    m = re.search(r"^undeclared_deviations:\s*(none|found)\s*$", s, re.M)
    return None if m is None else (m.group(1) == "found")


def _pipeline_version(c: _Ctx):
    return c.fm("intent", "pipeline") or PIPELINE_VERSION


def _task_ref(c: _Ctx):
    return c.fm("request", "source_ref")


def _verifications(c: _Ctx):
    """Projection of the verification records (D17). Log-derived, so always

    computable — an empty result is the meaningful claim "nothing was
    verified", not an absence. `standard_touched` is true if any check
    judged a diff that moved that check's own bar."""
    records = [d.data for d in c.log.of_type("verification")]
    by_verdict: dict[str, int] = {}
    by_verifier: dict[str, int] = {}
    for r in records:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
        by_verifier[r["verifier"]] = by_verifier.get(r["verifier"], 0) + 1
    return {
        "count": len(records),
        "by_verdict": dict(sorted(by_verdict.items())),
        "by_verifier": dict(sorted(by_verifier.items())),
        "standard_touched": any(r["standard_touched"] for r in records),
    }


def _disposition(c: _Ctx):
    """The lane this task ran under, and whether it was an override (D20).

    An escape hatch nobody can count is how `bypass` became invisible; this
    is the field that makes override rate a measurable quantity rather than
    a matter of trust. None means no disposition was recorded, which the
    frontier treats as `full`."""
    latest = c.log.latest("disposition")
    if latest is None:
        return None
    return {"lane": latest.data["lane"], "floor": latest.data["floor"],
            "overridden": "override_reason" in latest.data}


def _duration_by_phase(c: _Ctx):
    intent_ok = c.log.latest("intent_confirmed")
    plan_ok = c.log.latest("plan_approved")
    disposed = c.log.latest("disposition")
    produced = {a: c.fm(a, "produced_at") for a in
                ("intent", "findings", "plan", "ledger", "review")}
    # `implement` measures one concept on every lane: time spent implementing
    # after work was authorised. The authorising event differs — plan approval
    # on `full`, the disposition on `express`, where no plan exists — but the
    # quantity does not. Without the second anchor this metric is silently
    # null on express, biasing any later comparison between the lanes.
    authorised = (plan_ok.ts if plan_ok
                  else disposed.ts if disposed
                  else produced["plan"])
    name = c.dir.name
    return {
        "refine": _seconds(c.fm("request", "created_at"), produced["intent"],
                           label=f"{name}: duration_by_phase.refine"),
        "research": _seconds(intent_ok.ts if intent_ok else produced["intent"],
                             produced["findings"],
                             label=f"{name}: duration_by_phase.research"),
        "plan": _seconds(produced["findings"], produced["plan"],
                         label=f"{name}: duration_by_phase.plan"),
        "implement": _seconds(authorised, produced["ledger"],
                              label=f"{name}: duration_by_phase.implement"),
        "review": _seconds(produced["ledger"], produced["review"],
                           label=f"{name}: duration_by_phase.review"),
    }


METRICS = {
    "intent_request_delta": _intent_request_delta,
    "nongoals_count": _nongoals_count,
    "intent_edited_at_gate": lambda c: _gate_edited(c, "intent_confirmed"),
    "blocking_questions_count": _blocking_questions_count,
    "assumptions_unverified_count": _assumptions_unverified_count,
    "plan_edited_at_gate": lambda c: _gate_edited(c, "plan_approved"),
    "out_of_scope_count": _out_of_scope_count,
    "escalations": _escalations,
    "ledger_entries": _ledger_entries,
    "self_corrections": _self_corrections,
    "verdict_sequence": _verdict_sequence,
    "undeclared_deviations_found": _undeclared_deviations_found,
    "pipeline": _pipeline_version,
    "task_ref": _task_ref,
    "duration_by_phase": _duration_by_phase,
    "verifications": _verifications,
    "disposition": _disposition,
}


# --------------------------------------------------------------------------
# Extraction & idempotent append
# --------------------------------------------------------------------------

def _outcome(c: _Ctx) -> str:
    # Precedence mirrors the frontier's terminal ordering (BYPASSED > DONE)
    # so the two components can never disagree about a task's end state.
    bypass = c.log.latest("bypass")
    req = c.dir / SCHEMAS["request"].filename
    if (bypass is not None and req.exists()
            and bypass.data.get("request_hash") == art.sha256(req)):
        return "bypassed"
    merged = c.log.latest("merged")
    if merged is not None:
        return f"merged:{merged.data['commit']}"
    raise ExtractionError(
        f"{c.dir.name}: not extractable — telemetry is written at merge "
        "(record a 'merged' decision first) or for bypassed tasks")


def extract(task_dir: str | Path) -> dict:
    """Pure projection: one record answering every metric the contracts

    declared, plus the envelope (task, outcome). No wall clock."""
    c = _Ctx(Path(task_dir))
    record: dict = {"task": Path(task_dir).name, "outcome": _outcome(c)}
    ordered = list(TASK_TELEMETRY_METRICS)
    for contract in CONTRACT_TELEMETRY:            # contract blocks drive it
        ordered.extend(CONTRACT_TELEMETRY[contract])
    for metric_id in ordered:
        record[metric_id] = METRICS[metric_id](c)
    return record


def append(record: dict, path: str | Path = DEFAULT_PATH) -> bool:
    """Append-only, idempotent on (task, outcome). Returns True if a

    record was written, False if the key already existed."""
    p = Path(path)
    key = (record["task"], record["outcome"])
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (existing.get("task"), existing.get("outcome")) == key:
                return False
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return True
