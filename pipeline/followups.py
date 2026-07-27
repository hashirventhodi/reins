"""Deterministic follow-up harvesting (Tier 1; D14).

Answers exactly one question: "which follow-up candidates does this
task's artifact chain contain?" A pure, read-only projection — the same
guarantees as frontier and telemetry: identical inputs yield
byte-identical output, no wall clock, no absolute paths, filesystem
untouched.

Normative extraction rules (documented in docs/followups.md):
  order    — artifact chain order (intent, findings, ledger, review),
             document order within each artifact;
  intent   — "Non-goals" bullets matching /defer/i;
  findings — every "Out-of-scope observations" bullet;
  ledger   — entries whose plan_impact != "none", rendered by a fixed
             template;
  review   — "Findings" bullets tagged should-fix:/nit: (blocking
             findings block; they are not follow-ups);
  dedup    — exact match on normalized text (prefix-stripped,
             lowercased, whitespace-collapsed, trailing period dropped);
             first occurrence wins and accumulates origins. No fuzzy
             matching: near-duplicates are the human's call;
  title    — cleaned text, word-boundary truncated to <=72 chars;
  body     — the artifact text VERBATIM + a fixed origin line;
  already_created — a sibling task whose source_ref is
             "followup:<this task>" and whose request body starts with
             the candidate body marks the candidate as created.

Creation is orchestration and belongs to the runtime (D14 as amended,
per the D12 precedent): the runtime relays the human's explicit
selection by invoking `pipeline task add` once per candidate, extracting
title/body from this module's JSON MECHANICALLY (jq/python), never by
retyping. `creation_body()` below is the normative byte spec a created
follow-up's request body must satisfy; already-created detection depends
on it.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import artifact as art
from .errors import PipelineError
from .schemas import SCHEMAS
from .validate import _bullet_blocks

SOURCE_ORDER = ("intent", "findings", "ledger", "review")
TITLE_MAX = 72

_DEFER_RE = re.compile(r"defer", re.I)
_SEVERITY_RE = re.compile(r"^-\s*(should-fix|nit):", re.I)
_PREFIX_RE = re.compile(
    r"^(\[(?:non-)?blocking\]\s*|\[(?:un)?verified\]\s*|(?:should-fix|nit):\s*)+",
    re.I)


def _clean(block: str) -> str:
    s = re.sub(r"^-\s*", "", block.strip())
    s = _PREFIX_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm(block: str) -> str:
    return _clean(block).lower().rstrip(".")


def _title(block: str) -> str:
    s = _clean(block)
    if len(s) <= TITLE_MAX:
        return s
    cut = s.rfind(" ", 0, TITLE_MAX)
    return s[: cut if cut > 0 else TITLE_MAX].rstrip() + "…"


def _load(task_dir: Path, atype: str) -> art.Artifact | None:
    path = task_dir / SCHEMAS[atype].filename
    if not path.exists():
        return None
    try:
        return art.load(path)
    except Exception:
        return None


def _raw_candidates(task_dir: Path) -> list[dict]:
    out: list[dict] = []

    a = _load(task_dir, "intent")
    if a is not None:
        for block in _bullet_blocks(a.sections.get("Non-goals", "")):
            if _DEFER_RE.search(block):
                out.append({"body": block, "origin": {
                    "artifact": "intent", "section": "Non-goals"}})

    a = _load(task_dir, "findings")
    if a is not None:
        for block in _bullet_blocks(
                a.sections.get("Out-of-scope observations", "")):
            out.append({"body": block, "origin": {
                "artifact": "findings",
                "section": "Out-of-scope observations"}})

    a = _load(task_dir, "ledger")
    if a is not None:
        try:
            entries = art.ledger_entries(a)
        except Exception:
            entries = []
        for i, e in enumerate(entries, 1):
            impact = str(e.get("plan_impact", "none")).strip()
            if impact == "none":
                continue
            body = (f"Deferred consequence of step {e['step']}: {e['what']} "
                    f"— {e['why']} (plan impact: {impact})")
            out.append({"body": body, "origin": {
                "artifact": "ledger", "entry": i}})

    a = _load(task_dir, "review")
    if a is not None:
        for block in _bullet_blocks(a.sections.get("Findings", "")):
            m = _SEVERITY_RE.match(block)
            if m:
                out.append({"body": block, "origin": {
                    "artifact": "review", "section": "Findings",
                    "severity": m.group(1).lower()}})
    return out


def _already_created(task_dir: Path, body: str) -> str | None:
    parent = task_dir.parent
    ref = f"followup:{task_dir.name}"
    if not parent.is_dir():
        return None
    for sibling in sorted(p for p in parent.iterdir() if p.is_dir()):
        if sibling.name == task_dir.name:
            continue
        req = sibling / "request.md"
        if not req.exists():
            continue
        try:
            a = art.load(req)
        except Exception:
            continue
        if a.frontmatter.get("source_ref") != ref:
            continue
        if art.body_text(a).strip().startswith(body.strip()):
            return sibling.name
    return None


def harvest(task_dir: str | Path) -> dict:
    """Pure projection: the deterministic candidate list."""
    d = Path(task_dir)
    if not d.is_dir():
        raise PipelineError(f"no such task directory: {d}")
    seen: dict[str, dict] = {}
    order: list[str] = []
    for raw in _raw_candidates(d):
        key = _norm(raw["body"])
        if not key:
            continue
        if key in seen:
            seen[key]["origins"].append(raw["origin"])
            continue
        seen[key] = {"title": _title(raw["body"]), "body": raw["body"],
                     "origins": [raw["origin"]]}
        order.append(key)
    candidates = []
    for index, key in enumerate(order, 1):
        c = seen[key]
        candidates.append({
            "index": index,
            "title": c["title"],
            "body": c["body"],
            "origins": c["origins"],
            "already_created": _already_created(d, c["body"]),
        })
    return {"task": d.name, "candidates": candidates}


def creation_body(candidate: dict, parent_task: str) -> str:
    """The exact bytes a created follow-up's request body must contain."""
    return f"{candidate['body']}\n\nOrigin: review of {parent_task}\n"
