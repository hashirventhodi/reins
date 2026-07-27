"""M0 acceptance: round-trip parse/serialize on all fixture artifacts,

typed all-or-nothing failure on malformed input, hashing over exact bytes,
fence-aware section splitting, ledger entry parsing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline import artifact
from pipeline.errors import ArtifactParseError, LedgerFormatError

ROOT = Path(__file__).resolve().parent.parent
HAPPY = ROOT / "tests" / "fixtures" / "happy"
MALFORMED = ROOT / "tests" / "fixtures" / "malformed"
CONTRACTS = ROOT / "contracts"

FIXTURE_FILES = sorted(HAPPY.rglob("*.md"))
CONTRACT_FILES = sorted(CONTRACTS.glob("*.md"))
ALL_PARSEABLE = FIXTURE_FILES + CONTRACT_FILES

assert FIXTURE_FILES, "happy fixtures missing — run scripts/regen_fixtures.py"


@pytest.mark.parametrize("path", ALL_PARSEABLE, ids=lambda p: p.name)
def test_roundtrip_identity(path: Path):
    """load(dump(load(f))) == load(f) on frontmatter, preamble, sections."""
    first = artifact.load(path)
    second = artifact.loads(artifact.dumps(first), str(path))
    assert second.frontmatter == first.frontmatter
    assert second.preamble == first.preamble
    assert second.sections == first.sections


@pytest.mark.parametrize("path", ALL_PARSEABLE, ids=lambda p: p.name)
def test_body_is_byte_preserved(path: Path):
    """Preamble + sections reproduce the original body verbatim."""
    text = path.read_text(encoding="utf-8")
    a = artifact.load(path)
    body = text.split("\n---\n", 1)[1]
    reconstructed_parts = []
    if a.preamble or not a.sections:
        reconstructed_parts.append(a.preamble)
    for name, content in a.sections.items():
        reconstructed_parts.append(f"## {name}")
        reconstructed_parts.append(content)
    assert "\n".join(reconstructed_parts) == body


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name)
def test_parse_does_not_mutate(path: Path):
    before = path.read_bytes()
    artifact.load(path)
    assert path.read_bytes() == before


def test_sha256_is_over_exact_bytes(tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_bytes(b"---\ntask: t\n---\nbody\n")
    expected = hashlib.sha256(f.read_bytes()).hexdigest()
    assert artifact.sha256(f) == f"sha256:{expected}"
    # A single byte change changes the hash (trailing whitespace matters:
    # intent_request_delta depends on byte-exact preservation).
    f.write_bytes(b"---\ntask: t\n---\nbody \n")
    assert artifact.sha256(f) != f"sha256:{expected}"


def test_heading_inside_fence_is_content():
    text = (
        "---\npipeline: 1\n---\n"
        "## Real\n"
        "```md\n## Fake heading inside fence\n```\n"
        "after\n"
    )
    a = artifact.loads(text)
    assert list(a.sections) == ["Real"]
    assert "## Fake heading inside fence" in a.sections["Real"]


def test_empty_frontmatter_roundtrip():
    a = artifact.loads("---\n---\nno sections here\n")
    assert a.frontmatter == {}
    assert a.sections == {}
    b = artifact.loads(artifact.dumps(a))
    assert (b.frontmatter, b.preamble, b.sections) == (
        a.frontmatter, a.preamble, a.sections
    )


MALFORMED_CASES = [
    "bad-frontmatter.md",
    "not-a-mapping.md",
    "no-close.md",
    "duplicate-section.md",
    "no-frontmatter.md",
    "not-utf8.md",
]


@pytest.mark.parametrize("name", MALFORMED_CASES)
def test_malformed_raises_typed_error(name: str):
    with pytest.raises(ArtifactParseError) as exc:
        artifact.load(MALFORMED / name)
    assert name in exc.value.path
    assert exc.value.message  # human-quotable, per blueprint §5


def test_consumed_hashes_happy_chain():
    task_dir = next(HAPPY.iterdir())
    findings = artifact.load(task_dir / "findings.md")
    pins = artifact.consumed_hashes(findings)
    assert set(pins) == {"request", "intent"}
    assert pins["request"] == artifact.sha256(task_dir / "request.md")
    assert pins["intent"] == artifact.sha256(task_dir / "intent.md")


def test_consumed_hashes_rejects_malformed_entries():
    a = artifact.loads(
        "---\nconsumes:\n- artifact: intent\n---\n## S\nx\n", "mem.md"
    )
    with pytest.raises(ArtifactParseError):
        artifact.consumed_hashes(a)
    b = artifact.loads(
        "---\nconsumes:\n- artifact: intent\n  hash: h1\n"
        "- artifact: intent\n  hash: h2\n---\n## S\nx\n", "mem.md"
    )
    with pytest.raises(ArtifactParseError):
        artifact.consumed_hashes(b)


def test_ledger_entries_parse_and_validate():
    task_dir = next(HAPPY.iterdir())
    entries = artifact.ledger_entries(artifact.load(task_dir / "ledger.md"))
    assert len(entries) == 1
    assert entries[0]["status"] == "within-autonomy"


def test_empty_ledger_is_valid_and_blank_is_not():
    fm = "---\npipeline: 1\n---\n"
    empty = artifact.loads(fm + "## Entries\n```yaml\n[]\n```\n", "l.md")
    assert artifact.ledger_entries(empty) == []
    blank = artifact.loads(fm + "## Entries\n\n", "l.md")
    with pytest.raises(LedgerFormatError):
        artifact.ledger_entries(blank)  # empty list is a claim, not an omission


def test_ledger_rejects_bad_status_and_missing_fields():
    fm = "---\npipeline: 1\n---\n## Entries\n"
    bad_status = fm + (
        "```yaml\n- step: '1'\n  what: w\n  why: y\n  plan_impact: none\n"
        "  status: freestyle\n```\n"
    )
    with pytest.raises(LedgerFormatError):
        artifact.ledger_entries(artifact.loads(bad_status, "l.md"))
    missing = fm + "```yaml\n- step: '1'\n  what: w\n```\n"
    with pytest.raises(LedgerFormatError):
        artifact.ledger_entries(artifact.loads(missing, "l.md"))
