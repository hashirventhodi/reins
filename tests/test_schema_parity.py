"""Parity snapshot (risk R1): the canonical contract texts and schemas.py

declare the same facts. If prose and code drift, this fails CI. Also
checks the fixture chain conforms to the declared schemas — fixtures are
the executable specification."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import artifact, schemas

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / "contracts"
HAPPY = ROOT / "tests" / "fixtures" / "happy"
EXPRESS = ROOT / "tests" / "fixtures" / "express"


def contract_fm(name: str) -> dict:
    return artifact.load(CONTRACTS_DIR / f"{name}.md").frontmatter


def test_every_contract_has_a_text_and_vice_versa():
    files = {p.stem for p in CONTRACTS_DIR.glob("*.md")}
    assert files == set(schemas.CONTRACTS)


def test_pipeline_version_file_matches_registry():
    on_disk = (CONTRACTS_DIR / "PIPELINE_VERSION").read_text().strip()
    assert int(on_disk) == schemas.PIPELINE_VERSION


@pytest.mark.parametrize("contract", schemas.CONTRACTS)
def test_contract_frontmatter_matches_schema(contract: str):
    fm = contract_fm(contract)
    produced = schemas.CONTRACT_PRODUCES[contract]
    schema = schemas.SCHEMAS[produced]

    assert fm["contract"] == contract
    assert fm["produces"] == produced
    assert tuple(fm["consumes"]) == schema.consumes_spec
    # D21: the alternate pin set is declared in both places or neither
    if schema.consumes_alt is None:
        assert "consumes_express" not in fm, contract
    else:
        assert tuple(fm["consumes_express"]) == schema.consumes_alt, contract
    assert tuple(fm["artifact_sections"]) == schema.required_sections
    assert fm["gate"] == schemas.CONTRACT_GATES[contract]
    assert all(t in schemas.CONTRACTS for t in fm["backward"])
    assert tuple(fm["backward"]) == schemas.CONTRACT_BACKWARD[contract]
    assert tuple(fm["telemetry"]) == schemas.CONTRACT_TELEMETRY[contract]
    for metric in fm["telemetry"]:
        assert metric in schemas.CONTRACT_TELEMETRY_METRICS


def test_gates_are_valid_decision_types():
    for gate in schemas.CONTRACT_GATES.values():
        assert gate is None or gate in schemas.DECISION_TYPES


def test_execution_contract_escalations_match_registry():
    fm = contract_fm("execution")
    assert tuple(fm["escalations"]) == tuple(schemas.ESCALATIONS)
    text = (CONTRACTS_DIR / "execution.md").read_text(encoding="utf-8")
    for trigger, route in schemas.ESCALATION_ROUTES.items():
        assert f"**{trigger}**" in text
        assert route in ("planning", "human")


def test_review_contract_verdicts_match_registry():
    fm = contract_fm("review")
    assert tuple(fm["verdicts"]) == schemas.VERDICTS
    text = (CONTRACTS_DIR / "review.md").read_text(encoding="utf-8")
    for verdict in schemas.VERDICTS:
        assert f"`{verdict}`" in text


def test_intent_contract_no_longer_owns_the_entry_gate():
    """D22: the typed early return `Refine(request) -> intent.md | bypass`

    is retired. The threshold is computed (a floor) and disposed (a lane),
    both before this contract runs — so the contract text must not still
    advertise a bypass branch."""
    assert contract_fm("intent")["bypass"] is False
    text = (CONTRACTS_DIR / "intent.md").read_text(encoding="utf-8")
    assert "the entry gate no longer lives here" in text
    assert "express" in text


def test_consumes_graph_is_acyclic_and_upstream_only():
    order = {name: i for i, name in enumerate(schemas.CHAIN)}
    for schema in schemas.SCHEMAS.values():
        for consumed in schema.consumes_spec:
            if consumed in schemas.VIRTUAL_ARTIFACTS:
                continue
            assert order[consumed] < order[schema.artifact], (
                f"{schema.artifact} consumes downstream artifact {consumed}"
            )


# --- fixtures conform to schemas (executable specification) ---------------

def task_dir() -> Path:
    dirs = sorted(d for d in HAPPY.iterdir() if d.is_dir())
    assert dirs, "no happy fixture — run scripts/regen_fixtures.py"
    return dirs[0]


@pytest.mark.parametrize("artifact_type", schemas.CHAIN)
def test_fixture_artifact_conforms(artifact_type: str):
    schema = schemas.SCHEMAS[artifact_type]
    a = artifact.load(task_dir() / schema.filename)

    for fld in schema.frontmatter_fields:
        assert fld in a.frontmatter, f"{schema.filename} missing '{fld}'"
    for section in schema.required_sections:
        assert section in a.sections, f"{schema.filename} missing '## {section}'"

    if artifact_type == "request":
        assert "consumes" not in a.frontmatter  # V3: the source pins nothing
        return

    assert a.frontmatter["pipeline"] == schemas.PIPELINE_VERSION
    assert a.frontmatter["contract"] == schema.produced_by
    pins = artifact.consumed_hashes(a)
    assert set(pins) == set(schema.consumes_spec)
    for upstream, digest in pins.items():
        if upstream in schemas.VIRTUAL_ARTIFACTS:
            # D16: a git object reference, in the shape production emits —
            # 'sha256:' here would be a content hash the diff never has.
            assert digest.startswith(schemas.GIT_REF_PREFIX)
            assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}",
                                digest[len(schemas.GIT_REF_PREFIX):])
            continue
        actual = artifact.sha256(task_dir() / schemas.SCHEMAS[upstream].filename)
        assert digest == actual, (
            f"{schema.filename} pins stale {upstream} hash — regen fixtures"
        )


@pytest.mark.parametrize("artifact_type", schemas.LANE_CHAINS["express"])
def test_express_fixture_conforms(artifact_type: str):
    """The express fixture is a second executable specification: its pins

    must be the *alternate* set, and every hash real (D21)."""
    d = sorted(x for x in EXPRESS.iterdir() if x.is_dir())[0]
    schema = schemas.SCHEMAS[artifact_type]
    a = artifact.load(d / schema.filename)
    for section in schema.required_sections:
        assert section in a.sections
    if artifact_type == "request":
        assert "consumes" not in a.frontmatter
        return
    pins = artifact.consumed_hashes(a)
    assert set(pins) == set(schema.consumes_alt), artifact_type
    for upstream, digest in pins.items():
        if upstream in schemas.VIRTUAL_ARTIFACTS:
            assert digest.startswith(schemas.GIT_REF_PREFIX)
            continue
        assert digest == artifact.sha256(d / schemas.SCHEMAS[upstream].filename)


def test_express_fixture_omits_the_gated_artifacts():
    """The two consent gates cannot fire because their artifacts never

    exist — that is *how* express costs one human stop instead of three,
    rather than by suppressing a gate check."""
    d = sorted(x for x in EXPRESS.iterdir() if x.is_dir())[0]
    for gated in ("intent", "findings", "plan"):
        assert not (d / f"{gated}.md").exists()


def test_fixture_review_fidelity_consistency():
    """G2/V6 on the fixture itself: the executable spec demonstrates the

    undeclared-deviations line and verdict consistency."""
    a = artifact.load(task_dir() / "review.md")
    fidelity = a.sections["Fidelity"]
    lines = [l.strip() for l in fidelity.splitlines()]
    marker = [l for l in lines if l.startswith("undeclared_deviations:")]
    assert len(marker) == 1
    value = marker[0].split(":", 1)[1].strip()
    assert value in schemas.UNDECLARED_DEVIATIONS_VALUES
    verdict = a.sections["Verdict"].strip()
    assert verdict in schemas.VERDICTS
    if value == "found":
        assert verdict != "approve"
