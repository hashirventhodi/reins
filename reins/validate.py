"""The validator (M1). Answers exactly one question:

    "Is the current state internally valid?"

It never computes workflow progression — frontier (M2) owns "what happens
next." The validator only reads; it never writes (purity is tested).

Levels (blueprint §5):
  - artifact level: parse, frontmatter typing, required sections,
    mechanical section rules, enums;
  - task level: consumes DAG vs consumes_spec, hash recomputation,
    transitive staleness, request immutability, cross-artifact rules.

Every check has a stable rule id (RULES below) so fixtures, waivers (M2)
and self-correcting skills can reference rules precisely. Violations are
typed, JSON-serializable, and carry a quotable message.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import artifact as art
from .errors import ArtifactParseError, LedgerFormatError
from .schemas import (
    CHAIN,
    CONTENT_REF_RE,
    GIT_REF_RE,
    PIPELINE_VERSION,
    SCHEMAS,
    UNDECLARED_DEVIATIONS_VALUES,
    VERDICTS,
    VIRTUAL_ARTIFACTS,
    ASSUMPTION_TAGS,
    QUESTION_TAGS,
)

# ---------------------------------------------------------------------------
# Rule registry: every violation the validator can emit.
# ---------------------------------------------------------------------------

RULES: dict[str, str] = {
    "parse": "file is not a structurally valid artifact",
    "frontmatter-missing-field": "required frontmatter field absent",
    "pipeline-version": "artifact pipeline version differs from the registry",
    "contract-mismatch": "frontmatter 'contract' is not this artifact's producer",
    "task-mismatch": "frontmatter 'task' differs from the task directory name",
    "request-consumes": "request.md must not declare consumes (it is the source)",
    "consumes-structure": "consumes[] is structurally malformed",
    "consumes-set": "consumes[] does not pin exactly the schema's consumes_spec",
    "hash-format": ("a pinned reference is malformed: content artifacts need "
                    "'sha256:<64 hex>', virtual artifacts 'git:<object id>'"),
    "section-missing": "a required section heading is absent",
    "section-empty": "a mandatory-nonempty section is blank",
    "referenced-claims": "a Current state bullet carries no path:line/doc reference",
    "assumption-untagged": "an Assumptions bullet lacks [verified]/[unverified]",
    "verified-unreferenced": "a [verified] assumption carries no reference",
    "question-untagged": "an Open questions bullet lacks [blocking]/[non-blocking]",
    "steps-empty": "the Steps section contains no numbered steps",
    "step-missing-verify": "a plan step has no 'verify:' line",
    "ledger-format": "the ledger Entries block is malformed",
    "fidelity-marker": "Fidelity lacks exactly one 'undeclared_deviations:' line",
    "verdict-invalid": "Verdict is not exactly one of the verdict enum",
    "verdict-fidelity": "undeclared_deviations: found cannot coexist with approve",
    "upstream-missing": "a pinned upstream artifact file does not exist",
    "unknown-artifact": "an unexpected .md file is present in the task directory",
    "stale": "a pinned upstream changed (or is itself stale/invalid)",
}

_HASH_RE = CONTENT_REF_RE       # D16: declared in schemas so nothing drifts
_GIT_REF_RE = GIT_REF_RE
# A reference token: something with a dot path (file or doc), optionally :line.
_REF_RE = re.compile(r"[\w./-]*\w\.\w[\w-]*(?::\d+)?")
_STEP_RE = re.compile(r"^\d+\.\s")
_FIDELITY_RE = re.compile(
    rf"^undeclared_deviations:\s*({'|'.join(UNDECLARED_DEVIATIONS_VALUES)})\s*$"
)

FRESH, MISSING, INVALID, STALE = "fresh", "missing", "invalid", "stale"


@dataclass(frozen=True)
class Violation:
    artifact: str          # artifact type ('request'…'review') or '<task>'
    rule: str
    message: str
    line: int | None = None

    def to_dict(self) -> dict:
        d = {"artifact": self.artifact, "rule": self.rule, "message": self.message}
        if self.line is not None:
            d["line"] = self.line
        return d


@dataclass
class ArtifactState:
    status: str
    violations: list[Violation] = field(default_factory=list)


@dataclass
class Report:
    task_dir: str
    artifacts: dict[str, ArtifactState]
    task_violations: list[Violation] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """No artifact is invalid or stale, and no task-level violations.

        Missing downstream artifacts are VALID state: a partially built
        chain is simply a task in progress."""
        return not self.task_violations and all(
            s.status in (FRESH, MISSING) for s in self.artifacts.values()
        )

    def all_violations(self) -> list[Violation]:
        out = list(self.task_violations)
        for state in self.artifacts.values():
            out.extend(state.violations)
        return out

    def to_dict(self) -> dict:
        return {
            "task_dir": self.task_dir,
            "is_valid": self.is_valid,
            "artifacts": {
                name: {
                    "status": state.status,
                    "violations": [v.to_dict() for v in state.violations],
                }
                for name, state in self.artifacts.items()
            },
            "task_violations": [v.to_dict() for v in self.task_violations],
        }


# ---------------------------------------------------------------------------
# Section rule interpreters
# ---------------------------------------------------------------------------

# Markdown emphasis an author may wrap a token in. The tag and the verdict are
# the contract; how they are styled is not — and the contract texts themselves
# render both decorated, so a literal match rejects documents that follow the
# documentation (D28).
_DECOR = "*_`"


def _undecorate(text: str) -> str:
    """A token with surrounding whitespace and markdown emphasis removed."""
    return text.strip().strip(_DECOR).strip()


def _head_tag(block: str, tags: tuple[str, ...]) -> tuple[str | None, str]:
    """The tag opening a bullet, and the text after it.

    Matches `- [verified] …`, `- **[verified]** …` and ``- `[verified]` …``
    alike. Returns (None, "") when no tag opens the bullet."""
    if not block.startswith("- "):
        return None, ""
    head = block[2:].lstrip(_DECOR + " ")
    for t in tags:
        if head.startswith(t):
            return t, head[len(t):].lstrip(_DECOR + " ")
    return None, ""


def _bullet_blocks(content: str) -> list[str]:
    """Split section content into top-level '- ' bullet blocks (a bullet

    plus its indented continuation lines). Prose outside bullets is not a
    block."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in content.split("\n"):
        if line.startswith("- "):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None and (line.startswith("  ") or not line.strip()):
            current.append(line)
        else:
            if current is not None:
                blocks.append("\n".join(current))
                current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def _step_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in content.split("\n"):
        if _STEP_RE.match(line):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def _check_section_rule(atype: str, section: str, rule: str, content: str,
                        a: art.Artifact) -> list[Violation]:
    v: list[Violation] = []

    if rule == "nonempty":
        if not content.strip():
            v.append(Violation(atype, "section-empty",
                               f"section '{section}' must not be empty"))

    elif rule == "referenced-claims":
        for block in _bullet_blocks(content):
            if not _REF_RE.search(block):
                head = block.splitlines()[0][:60]
                v.append(Violation(atype, "referenced-claims",
                                   f"unreferenced claim: {head!r}"))

    elif rule == "tagged-assumptions":
        for block in _bullet_blocks(content):
            tag, rest = _head_tag(block, ASSUMPTION_TAGS)
            if tag is None:
                v.append(Violation(
                    atype, "assumption-untagged",
                    f"untagged assumption: {block[:60]!r} — every bullet must "
                    f"start with one of {' '.join(ASSUMPTION_TAGS)}"))
            elif tag == "[verified]" and not _REF_RE.search(rest):
                v.append(Violation(atype, "verified-unreferenced",
                                   f"[verified] without reference: {block[:60]!r}"))

    elif rule == "tagged-questions":
        for block in _bullet_blocks(content):
            if _head_tag(block, QUESTION_TAGS)[0] is None:
                v.append(Violation(
                    atype, "question-untagged",
                    f"untagged question: {block[:60]!r} — every bullet must "
                    f"start with one of {' '.join(QUESTION_TAGS)}"))

    elif rule == "verify-lines":
        steps = _step_blocks(content)
        if not steps:
            v.append(Violation(atype, "steps-empty",
                               "Steps contains no numbered steps"))
        for i, block in enumerate(steps, 1):
            if "verify:" not in block:
                v.append(Violation(atype, "step-missing-verify",
                                   f"step {i} has no 'verify:' line"))

    elif rule == "ledger-entries":
        try:
            art.ledger_entries(a)
        except LedgerFormatError as exc:
            v.append(Violation(atype, "ledger-format", exc.message))

    elif rule == "undeclared-deviations-line":
        markers = [l for l in (s.strip() for s in content.splitlines())
                   if l.startswith("undeclared_deviations:")]
        valid = [l for l in markers if _FIDELITY_RE.match(l)]
        if len(markers) != 1 or len(valid) != 1:
            v.append(Violation(
                atype, "fidelity-marker",
                "Fidelity must contain exactly one line "
                f"'undeclared_deviations: {'|'.join(UNDECLARED_DEVIATIONS_VALUES)}'"
                f" (found {len(markers)} marker line(s), {len(valid)} valid)"))

    elif rule == "verdict-enum":
        if _undecorate(content) not in VERDICTS:
            v.append(Violation(
                atype, "verdict-invalid",
                f"verdict {content.strip()!r} not in {VERDICTS} — the section "
                "must hold the bare token and nothing else; put rationale "
                "under another heading"))

    elif rule == "verdict-fidelity-consistency":
        verdict = _undecorate(content)
        fidelity = a.sections.get("Fidelity", "")
        found = any(_FIDELITY_RE.match(l.strip()) and "found" in l
                    for l in fidelity.splitlines())
        if found and verdict == "approve":
            v.append(Violation(atype, "verdict-fidelity",
                               RULES["verdict-fidelity"]))
    return v


# ---------------------------------------------------------------------------
# Artifact-level validation
# ---------------------------------------------------------------------------

def validate_artifact(path: str | Path, task_name: str | None = None
                      ) -> list[Violation]:
    """Schema validity of a single artifact file. Pure; read-only."""
    p = Path(path)
    atype = p.stem
    schema = SCHEMAS.get(atype)
    if schema is None:
        return [Violation(atype, "unknown-artifact",
                          f"no schema for artifact file {p.name!r}")]
    try:
        a = art.load(p)
    except ArtifactParseError as exc:
        return [Violation(atype, "parse", exc.message, exc.line)]

    v: list[Violation] = []
    for fld in schema.frontmatter_fields:
        if fld not in a.frontmatter:
            v.append(Violation(atype, "frontmatter-missing-field",
                               f"missing frontmatter field {fld!r}"))
    if task_name is not None and a.frontmatter.get("task") not in (None, task_name):
        v.append(Violation(atype, "task-mismatch",
                           f"frontmatter task {a.frontmatter.get('task')!r} "
                           f"!= directory {task_name!r}"))

    if atype == "request":
        if "consumes" in a.frontmatter:
            v.append(Violation(atype, "request-consumes", RULES["request-consumes"]))
        return v

    if "pipeline" in a.frontmatter and a.frontmatter["pipeline"] != PIPELINE_VERSION:
        v.append(Violation(atype, "pipeline-version",
                           f"artifact pipeline {a.frontmatter['pipeline']!r} "
                           f"!= registry {PIPELINE_VERSION}"))
    if ("contract" in a.frontmatter
            and a.frontmatter["contract"] != schema.produced_by):
        v.append(Violation(atype, "contract-mismatch",
                           f"contract {a.frontmatter['contract']!r} != "
                           f"producer {schema.produced_by!r}"))

    if "consumes" in a.frontmatter:
        try:
            pins = art.consumed_hashes(a)
        except ArtifactParseError as exc:
            v.append(Violation(atype, "consumes-structure", exc.message))
        else:
            # Either accepted pin set is structurally valid (D21). The
            # validator is file-only and cannot know the task's lane; the
            # frontier decides which shape the lane in force permits.
            accepted = [schema.consumes_spec]
            if schema.consumes_alt is not None:
                accepted.append(schema.consumes_alt)
            if not any(set(pins) == set(option) for option in accepted):
                expected = " or ".join(str(sorted(o)) for o in accepted)
                v.append(Violation(
                    atype, "consumes-set",
                    f"pins {sorted(pins)} != spec {expected}"))
            for upstream, digest in pins.items():
                # Virtual artifacts pin a git object id, not a content hash
                # (D16): different identity, different format.
                ref_re = (_GIT_REF_RE if upstream in VIRTUAL_ARTIFACTS
                          else _HASH_RE)
                if not ref_re.match(digest):
                    v.append(Violation(atype, "hash-format",
                                       f"pin for {upstream!r}: {digest!r}"))

    for section in schema.required_sections:
        if section not in a.sections:
            v.append(Violation(atype, "section-missing",
                               f"missing section '## {section}'"))
    for section, rules in schema.section_rules.items():
        if section not in a.sections:
            continue  # already reported as section-missing
        for rule in rules:
            v.extend(_check_section_rule(atype, section, rule,
                                         a.sections[section], a))
    return v


# ---------------------------------------------------------------------------
# Task-level validation
# ---------------------------------------------------------------------------

def validate_task(task_dir: str | Path) -> Report:
    """Classify every chain artifact {missing|invalid|stale|fresh} and

    collect task-level violations. Staleness is transitive: an artifact is
    stale if a pinned upstream's bytes changed, or a pinned upstream is
    itself stale or invalid (the blueprint's stale-cascade)."""
    d = Path(task_dir)
    task_name = d.name
    states: dict[str, ArtifactState] = {}

    for atype in CHAIN:
        path = d / SCHEMAS[atype].filename
        if not path.exists():
            states[atype] = ArtifactState(MISSING)
            continue
        violations = validate_artifact(path, task_name)
        if violations:
            states[atype] = ArtifactState(INVALID, violations)
            continue

        stale_v: list[Violation] = []
        if atype != "request":
            pins = art.consumed_hashes(art.load(path))
            for upstream, digest in pins.items():
                if upstream in VIRTUAL_ARTIFACTS:
                    continue  # diff freshness is git's domain (M2+)
                upath = d / SCHEMAS[upstream].filename
                if not upath.exists():
                    stale_v.append(Violation(atype, "upstream-missing",
                                             f"pins missing {upstream!r}"))
                    continue
                if art.sha256(upath) != digest:
                    stale_v.append(Violation(
                        atype, "stale",
                        f"pinned {upstream} hash no longer matches "
                        f"{upath.name} (consent/content changed upstream)"))
                elif states[upstream].status in (STALE, INVALID):
                    stale_v.append(Violation(
                        atype, "stale",
                        f"pinned {upstream} is itself {states[upstream].status}"))
        states[atype] = ArtifactState(STALE if stale_v else FRESH, stale_v)

    task_violations = [
        Violation("<task>", "unknown-artifact", f"unexpected file {p.name!r}")
        for p in sorted(d.glob("*.md"))
        if p.stem not in SCHEMAS
    ]
    return Report(str(d), states, task_violations)


def main(argv: list[str] | None = None) -> int:
    """Minimal entry point: ``python -m reins.validate <task_dir>``.

    Exit codes per blueprint §2.8: 0 valid, 1 usage, 2 violations."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m reins.validate <task_dir>", file=sys.stderr)
        return 1
    report = validate_task(args[0])
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.is_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
