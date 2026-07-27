"""Parse, serialize, and hash pipeline artifacts.

An artifact file is:

    ---
    <YAML mapping frontmatter>
    ---
    <optional preamble (e.g. an H1 title)>
    ## Section name
    section content
    ## Another section
    ...

Guarantees (blueprint §2.2):
  - Parsing never mutates files and is all-or-nothing (typed errors, no
    partial parses).
  - ``load(dump(load(f)))`` equals ``load(f)`` on frontmatter, preamble and
    sections; the *body* (preamble + sections) round-trips byte-identically.
    Frontmatter re-serialization is canonical YAML and may differ in style
    from the input; hashing is therefore always over exact file bytes,
    never over re-serialized content.
  - ``## `` lines inside fenced code blocks are content, not headings.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import miniyaml
from .errors import ArtifactParseError, LedgerFormatError
from .schemas import LEDGER_STATUSES

_FENCE_RE = re.compile(r"^(```+|~~~+)")
_HEADING_RE = re.compile(r"^## (?P<name>.+?)\s*$")

LEDGER_ENTRY_FIELDS = ("step", "what", "why", "plan_impact", "status")


@dataclass
class Artifact:
    """A parsed artifact. ``sections`` preserves file order and raw content

    (everything between one H2 heading and the next, verbatim)."""

    path: str
    frontmatter: dict
    preamble: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def artifact_type(self) -> str:
        """Filename stem, e.g. 'findings' for findings.md."""
        return Path(self.path).stem


def sha256(path: str | Path) -> str:
    """Content hash over exact file bytes, formatted 'sha256:<hex>'."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _split_frontmatter(text: str, path: str) -> tuple[dict, str, int]:
    """Return (frontmatter dict, body text, body start line)."""
    if not text.startswith("---\n") and text != "---":
        raise ArtifactParseError(path, "file must begin with '---' frontmatter fence", 1)
    lines = text.split("\n")
    close = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            close = i
            break
    if close is None:
        raise ArtifactParseError(path, "unterminated frontmatter: no closing '---'")
    fm_text = "\n".join(lines[1:close])
    try:
        fm = miniyaml.loads(fm_text)
    except miniyaml.MiniYamlError as exc:
        raise ArtifactParseError(path, f"invalid YAML frontmatter: {exc}") from exc
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise ArtifactParseError(
            path, f"frontmatter must be a mapping, got {type(fm).__name__}", 2
        )
    body = "\n".join(lines[close + 1:])
    return fm, body, close + 2  # 1-based line where the body starts


def _split_sections(body: str, path: str, body_start_line: int) -> tuple[str, dict[str, str]]:
    """Split the body into (preamble, {heading: raw content})."""
    preamble_lines: list[str] = []
    sections: dict[str, str] = {}
    current: str | None = None
    current_lines: list[str] = []
    in_fence = False
    fence_marker = ""

    def flush() -> None:
        nonlocal current_lines
        if current is not None:
            sections[current] = "\n".join(current_lines)
        current_lines = []

    for offset, line in enumerate(body.split("\n")):
        fence = _FENCE_RE.match(line.strip())
        if fence:
            marker = fence.group(1)[0] * 3
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif line.strip().startswith(fence_marker):
                in_fence = False
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading:
            name = heading.group("name")
            if name in sections or name == current:
                raise ArtifactParseError(
                    path, f"duplicate section heading '## {name}'",
                    body_start_line + offset,
                )
            flush()
            current = name
        elif current is None:
            preamble_lines.append(line)
        else:
            current_lines.append(line)
    flush()
    return "\n".join(preamble_lines), sections


def loads(text: str, path: str = "<memory>") -> Artifact:
    fm, body, body_line = _split_frontmatter(text, path)
    preamble, sections = _split_sections(body, path, body_line)
    return Artifact(path=path, frontmatter=fm, preamble=preamble, sections=sections)


def load(path: str | Path) -> Artifact:
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise ArtifactParseError(str(p), f"cannot read file: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactParseError(str(p), f"not valid UTF-8: {exc}") from exc
    return loads(text, str(p))


def dumps(a: Artifact) -> str:
    """Serialize. Body is reproduced verbatim; frontmatter is canonical

    YAML (safe_dump, insertion order preserved)."""
    fm = miniyaml.dumps(a.frontmatter).rstrip("\n") if a.frontmatter else ""
    parts = ["---", fm, "---"] if fm else ["---", "---"]
    body_parts: list[str] = []
    if a.preamble or not a.sections:
        body_parts.append(a.preamble)
    for name, content in a.sections.items():
        body_parts.append(f"## {name}")
        body_parts.append(content)
    return "\n".join(parts) + ("\n" + "\n".join(body_parts) if body_parts else "\n")


def dump(a: Artifact, path: str | Path) -> None:
    Path(path).write_bytes(dumps(a).encode("utf-8"))


def body_text(a: Artifact) -> str:
    """The artifact body (preamble + sections) reconstructed verbatim —

    the shared definition used by telemetry deltas and follow-up
    already-created matching (F4: preamble-only comparison was fragile
    when a body contains an '## ' line)."""
    parts = [a.preamble] if a.preamble else []
    parts += [f"## {n}\n{c}" for n, c in a.sections.items()]
    return "\n".join(parts)


def consumed_hashes(a: Artifact) -> dict[str, str]:
    """Return {artifact_type: hash} from a well-formed consumes[] list.

    Structural problems raise ArtifactParseError (validator relies on
    typed failure, not silent skipping)."""
    consumes = a.frontmatter.get("consumes", [])
    if not isinstance(consumes, list):
        raise ArtifactParseError(a.path, "frontmatter 'consumes' must be a list")
    out: dict[str, str] = {}
    for i, entry in enumerate(consumes):
        if (
            not isinstance(entry, dict)
            or set(entry) != {"artifact", "hash"}
            or not isinstance(entry.get("artifact"), str)
            or not isinstance(entry.get("hash"), str)
        ):
            raise ArtifactParseError(
                a.path,
                f"consumes[{i}] must be a mapping with exactly "
                "'artifact' and 'hash' string fields",
            )
        if entry["artifact"] in out:
            raise ArtifactParseError(
                a.path, f"consumes[] pins artifact '{entry['artifact']}' twice"
            )
        out[entry["artifact"]] = entry["hash"]
    return out


_YAML_FENCE_BLOCK_RE = re.compile(
    r"^\s*```(?:yaml|yml)?\s*\n(?P<body>.*?)\n?```\s*$", re.DOTALL
)


def ledger_entries(a: Artifact) -> list[dict]:
    """Parse the Entries section of ledger.md into entry dicts.

    The section contains a single fenced YAML block holding a list (possibly
    ``[]`` — the empty ledger is valid and meaningful: it is the signed
    claim that the diff matches the plan exactly)."""
    if "Entries" not in a.sections:
        raise LedgerFormatError(a.path, "ledger has no 'Entries' section")
    content = a.sections["Entries"].strip()
    if not content:
        raise LedgerFormatError(
            a.path,
            "Entries section is blank; an empty ledger must state '[]' "
            "explicitly inside a yaml fence (the empty list is a claim, "
            "not an omission)",
        )
    m = _YAML_FENCE_BLOCK_RE.match(content)
    if not m:
        raise LedgerFormatError(
            a.path, "Entries section must contain exactly one fenced yaml block"
        )
    try:
        data = miniyaml.loads(m.group("body")) or []
    except miniyaml.MiniYamlError as exc:
        raise LedgerFormatError(a.path, f"Entries yaml invalid: {exc}") from exc
    if not isinstance(data, list):
        raise LedgerFormatError(a.path, "Entries must be a yaml list")
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise LedgerFormatError(a.path, f"entry {i} is not a mapping")
        missing = [f for f in LEDGER_ENTRY_FIELDS if f not in entry]
        extra = [f for f in entry if f not in LEDGER_ENTRY_FIELDS]
        if missing or extra:
            raise LedgerFormatError(
                a.path,
                f"entry {i}: missing fields {missing or 'none'}, "
                f"unknown fields {extra or 'none'}",
            )
        if entry["status"] not in LEDGER_STATUSES:
            raise LedgerFormatError(
                a.path,
                f"entry {i}: status {entry['status']!r} not in {LEDGER_STATUSES}",
            )
    return data
