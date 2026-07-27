"""M4 acceptance: golden-record extraction (exact match — records contain

no wall clock), idempotent append keyed on (task, outcome), metric
registry generated from and complete against the contract telemetry
blocks, purity, and null-safety on bypassed tasks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline import artifact, cli, decisions as dec, telemetry as tele
from pipeline.schemas import ALL_TELEMETRY_METRICS, CONTRACT_TELEMETRY

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


@pytest.fixture()
def task(tmp_path: Path) -> Path:
    dst = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, dst)
    dec.append(dst, dec.make("merged", "2026-07-25T12:00:00Z",
                             commit="cafe123"))
    return dst


GOLDEN = {
    "task": HAPPY.name,
    "outcome": "merged:cafe123",
    "pipeline": 1,
    "task_ref": "local",
    "duration_by_phase": {"refine": 300, "research": 300, "plan": 480,
                          "implement": 1020, "review": 840},
    "verifications": {"count": 1, "by_verdict": {"pass": 1},
                      "by_verifier": {"tests": 1}, "standard_touched": True},
    "disposition": None,        # none recorded: the frontier reads that as full
    "intent_request_delta": None,   # filled below (computed, then frozen)
    "nongoals_count": 2,
    "intent_edited_at_gate": False,
    "blocking_questions_count": 0,
    "assumptions_unverified_count": 1,
    "plan_edited_at_gate": True,
    "out_of_scope_count": 3,
    "escalations": [],
    "ledger_entries": {"count": 1, "by_status": {"within-autonomy": 1}},
    "self_corrections": None,       # D13: no recording mechanism in v1
    "verdict_sequence": ["approve-with-fixes"],
    "undeclared_deviations_found": False,
}


def test_golden_record(task: Path):
    record = tele.extract(task)
    delta = record["intent_request_delta"]
    assert isinstance(delta, float) and 0.0 < delta < 1.0
    expected = dict(GOLDEN, intent_request_delta=delta)
    assert record == expected


def test_extraction_is_deterministic(task: Path, tmp_path: Path):
    other = tmp_path / "elsewhere" / task.name
    shutil.copytree(task, other)
    r1 = json.dumps(tele.extract(task), sort_keys=True)
    r2 = json.dumps(tele.extract(task), sort_keys=True)
    r3 = json.dumps(tele.extract(other), sort_keys=True)
    assert r1 == r2 == r3


def test_extraction_is_pure(task: Path):
    before = {p.name: p.read_bytes() for p in sorted(task.glob("*"))}
    tele.extract(task)
    assert {p.name: p.read_bytes() for p in sorted(task.glob("*"))} == before


def test_metric_registry_matches_declared_metrics():
    """Self-describing governance: exactly one function per declared

    metric ID; a contract declaring a new ID fails this until the
    function exists, and an undeclared function is equally rejected."""
    assert set(tele.METRICS) == set(ALL_TELEMETRY_METRICS)


def test_record_field_set_is_generated_from_contract_blocks(task: Path):
    record = tele.extract(task)
    declared = {m for ms in CONTRACT_TELEMETRY.values() for m in ms}
    assert declared <= set(record)
    assert set(record) == {"task", "outcome"} | set(ALL_TELEMETRY_METRICS)


def test_not_extractable_before_merge(tmp_path: Path):
    dst = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, dst)               # AWAITING_MERGE, no merged
    with pytest.raises(tele.ExtractionError, match="not extractable"):
        tele.extract(dst)


def test_bypassed_task_extracts_with_nulls(tmp_path: Path):
    d = tmp_path / "T-2026-07-25-tiny"
    d.mkdir()
    (d / "request.md").write_text(
        "---\ntask: T-2026-07-25-tiny\nsource_ref: local\n"
        "created_at: 2026-07-25T09:00:00Z\n---\nFix a typo.\n")
    dec.append(d, dec.make("bypass", "2026-07-25T09:01:00Z",
                           request_hash=artifact.sha256(d / "request.md"),
                           reason="single-file fix"))
    record = tele.extract(d)
    assert record["outcome"] == "bypassed"
    assert record["intent_request_delta"] is None
    assert record["nongoals_count"] is None
    assert record["verdict_sequence"] == []
    assert record["task_ref"] == "local"


EXPRESS = next((ROOT / "tests" / "fixtures" / "express").iterdir())


def test_implement_duration_is_measured_on_both_lanes(tmp_path: Path):
    """D24: `implement` means "time spent implementing after work was

    authorised" on every lane. The authorising event differs — plan approval
    on full, the disposition on express — but the quantity does not. Left
    unanchored, the metric is silently null on express and biases every
    later comparison between the lanes."""
    dst = tmp_path / EXPRESS.name
    shutil.copytree(EXPRESS, dst)
    dec.append(dst, dec.make("merged", "2026-07-25T09:30:00Z", commit="c0ffee"))
    phases = tele.extract(dst)["duration_by_phase"]

    # disposition 09:05 -> ledger 09:12
    assert phases["implement"] == 420
    assert phases["review"] == 480
    # the phases that genuinely did not happen stay null — that is honest,
    # not a gap (the D13 precedent)
    assert phases["refine"] is None
    assert phases["research"] is None
    assert phases["plan"] is None

    # on the full lane the plan approval still wins over any disposition
    happy = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, happy)
    dec.append(happy, dec.make("disposition", "2026-07-25T09:00:00Z",
                               lane="full", floor="full"))
    dec.append(happy, dec.make("merged", "2026-07-25T12:00:00Z", commit="d0d0"))
    assert tele.extract(happy)["duration_by_phase"]["implement"] == 1020


def test_negative_duration_emits_null_and_a_warning_not_an_impossible_value(
    tmp_path: Path,
):
    """D27: a phase duration can never legitimately be negative -- nothing

    finishes before it starts. Discovered via real usage: a hand-authored
    ledger.md `produced_at` carried the wrong UTC offset (a local wall-clock
    reading mislabeled with a `+00:00` suffix), landing *after* review.md's
    correctly-stamped `produced_at` and producing a nonsensical negative
    `review` duration with nothing to catch it. The fix treats a negative
    delta as invalid input, not a small measurement: emit None (the
    existing "cannot be computed" contract) plus a warning, and continue
    extracting every other metric."""
    dst = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, dst)
    ledger = dst / "ledger.md"
    # review.md's produced_at is 09:55:00Z (see the fixture); push ledger's
    # past it so `review = review.produced_at - ledger.produced_at` goes
    # negative, exactly the shape of the real bug.
    ledger.write_text(
        ledger.read_text().replace(
            "produced_at: 2026-07-25T09:41:00Z",
            "produced_at: 2026-07-25T10:00:00Z",
        )
    )
    dec.append(dst, dec.make("merged", "2026-07-25T12:00:00Z", commit="cafe123"))

    with pytest.warns(UserWarning, match="negative duration"):
        record = tele.extract(dst)

    assert record["duration_by_phase"]["review"] is None
    # every other metric still extracts -- one invalid phase never blocks
    # the rest of the record (the same non-blocking contract as any other
    # metric that "cannot be computed")
    assert record["duration_by_phase"]["plan"] == 480
    assert record["outcome"] == "merged:cafe123"


def test_verifications_projection_is_always_computable(tmp_path: Path):
    """Log-derived like _escalations, so it never emits None: "nothing was

    verified" is a claim worth recording, and count 0 states it. Contrast
    _ledger_entries, which is artifact-derived and None when absent."""
    d = tmp_path / "T-2026-07-25-tiny"
    d.mkdir()
    (d / "request.md").write_text(
        "---\ntask: T-2026-07-25-tiny\nsource_ref: local\n"
        "created_at: 2026-07-25T09:00:00Z\n---\nFix a typo.\n")
    dec.append(d, dec.make("merged", "2026-07-25T09:30:00Z", commit="c0ffee"))
    assert tele.extract(d)["verifications"] == {
        "count": 0, "by_verdict": {}, "by_verifier": {},
        "standard_touched": False}

    # multiple verifiers and a repeat both group deterministically
    for verifier, verdict in (("tests", "fail"), ("tests", "pass"),
                              ("security", "inconclusive")):
        dec.append(d, dec.make(
            "verification", "2026-07-25T09:20:00Z", verifier=verifier,
            tool="t 1.0", predicate="p", verdict=verdict,
            tree_ref="git:" + "a" * 40,
            evidence_hash="sha256:" + "b" * 64, standard_touched=False))
    assert tele.extract(d)["verifications"] == {
        "count": 3,
        "by_verdict": {"fail": 1, "inconclusive": 1, "pass": 1},
        "by_verifier": {"security": 1, "tests": 2},
        "standard_touched": False}


def test_append_is_idempotent(task: Path, tmp_path: Path):
    log = tmp_path / "telemetry.jsonl"
    record = tele.extract(task)
    assert tele.append(record, log) is True
    assert tele.append(record, log) is False
    assert tele.append(dict(record, outcome="merged:other"), log) is True
    lines = [l for l in log.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_append_survives_corrupt_lines(task: Path, tmp_path: Path):
    log = tmp_path / "telemetry.jsonl"
    log.write_text("{corrupt\n")
    assert tele.append(tele.extract(task), log) is True
    assert tele.append(tele.extract(task), log) is False


def test_verdict_sequence_includes_returned_history(task: Path):
    dec.append(task, dec.make("returned", "2026-07-25T11:00:00Z",
                              to_contract="execution",
                              reason="blocking findings",
                              verdict="return-to-implement",
                              review_hash="sha256:" + "a" * 64))
    record = tele.extract(task)
    assert record["verdict_sequence"] == ["return-to-implement",
                                          "approve-with-fixes"]


def test_cli_extract_append_idempotent(tmp_path: Path, capsys):
    repo = tmp_path
    assert cli.main(["--root", str(repo), "init"]) == 0
    dst = repo / ".dev" / "tasks" / HAPPY.name
    shutil.copytree(HAPPY, dst)
    root = ["--root", str(repo)]
    assert cli.main([*root, "extract", HAPPY.name]) == 2   # not merged yet
    capsys.readouterr()
    assert cli.main([*root, "decide", "merged", HAPPY.name,
                     "--commit", "cafe123"]) == 0
    assert cli.main([*root, "extract", HAPPY.name, "--append"]) == 0
    assert cli.main([*root, "extract", HAPPY.name, "--append"]) == 0
    lines = [l for l in (repo / "telemetry.jsonl").read_text().splitlines()
             if l.strip()]
    assert len(lines) == 1
    err = capsys.readouterr().err
    assert "already recorded" in err


def test_outcome_precedence_matches_frontier(task: Path):
    """F2 parity guard: BYPASSED outranks DONE in the frontier, so a

    task carrying both decisions must extract as bypassed, never as
    merged — the two components may not disagree about terminal state."""
    dec.append(task, dec.make("bypass", "2026-07-25T13:00:00Z",
                              request_hash=artifact.sha256(task / "request.md"),
                              reason="pathological double-terminal"))
    from pipeline import frontier as fr
    assert fr.frontier(task).status == "BYPASSED"
    assert tele.extract(task)["outcome"] == "bypassed"
