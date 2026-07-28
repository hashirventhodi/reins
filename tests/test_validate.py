"""M1 acceptance: every validator rule has a passing fixture (the happy

chain validates clean) and a failing fixture (a targeted mutation fires
exactly that rule); the validator is pure (fs byte-identical after runs);
staleness cascades; the entry point's exit codes hold; and the registry's
graph invariants reject broken architectures."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from reins import artifact, schemas, validate
from reins.errors import SchemaError
from reins.validate import FRESH, INVALID, MISSING, STALE

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


@pytest.fixture()
def task(tmp_path: Path) -> Path:
    dst = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, dst)
    return dst


def edit(path: Path, old, new=None) -> None:
    pairs = old if isinstance(old, list) else [(old, new)]
    text = path.read_text(encoding="utf-8")
    for o, n in pairs:
        assert o in text, f"mutation anchor missing in {path.name}: {o!r}"
        text = text.replace(o, n, 1)
    path.write_text(text, encoding="utf-8")


def fired(report: validate.Report) -> set[tuple[str, str]]:
    return {(v.artifact, v.rule) for v in report.all_violations()}


# --- passing fixture -------------------------------------------------------

def test_happy_chain_is_valid(task: Path):
    report = validate.validate_task(task)
    assert report.is_valid, report.to_dict()
    assert all(s.status == FRESH for s in report.artifacts.values())


def test_partial_chain_is_valid_state(task: Path):
    (task / "review.md").unlink()
    (task / "ledger.md").unlink()
    report = validate.validate_task(task)
    assert report.is_valid
    assert report.artifacts["ledger"].status == MISSING
    assert report.artifacts["review"].status == MISSING


# --- failing fixtures: one mutation per rule -------------------------------
# (file, mutation old->new or callable, expected (artifact, rule),
#  expected status of that artifact)

def M(file, old, new, artifact_type, rule, status=INVALID):
    return pytest.param((file, old, new), (artifact_type, rule), status, id=rule)


MATRIX = [
    M("findings.md", "---\npipeline", "---\npipeline: [\npipeline",
      "findings", "parse"),
    M("plan.md", "task: T-2026-07-25-request-id-header\n", "",
      "plan", "frontmatter-missing-field"),
    M("intent.md", "pipeline: 1", "pipeline: 99",
      "intent", "pipeline-version"),
    M("intent.md", "contract: intent", "contract: planning",
      "intent", "contract-mismatch"),
    M("intent.md", "task: T-2026-07-25-request-id-header",
      "task: T-somewhere-else", "intent", "task-mismatch"),
    M("request.md", "created_at: 2026-07-25T09:00:00Z",
      "created_at: 2026-07-25T09:00:00Z\nconsumes: []",
      "request", "request-consumes"),
    M("findings.md", "  hash: sha256:", "  hsah: sha256:",
      "findings", "consumes-structure"),
    M("findings.md", "- artifact: intent\n", "- artifact: plan\n",
      "findings", "consumes-set"),
    M("ledger.md", "- artifact: plan\n  hash: sha256:",
      "- artifact: plan\n  hash: sha1:",
      "ledger", "hash-format"),
    M("intent.md", "## Non-goals", "## Non-goals-renamed",
      "intent", "section-missing"),
    M("plan.md",
      "## Out of scope\n- Trusting/propagating inbound X-Request-Id.\n"
      "- Worker-process log binding.\n"
      "- Any log cleanup (per intent non-goals).",
      "## Out of scope\n", "plan", "section-empty"),
    M("findings.md", "- HTTP handling is centralized in a middleware stack "
      "(src/api/app.py:41).", "- HTTP handling is centralized somewhere.",
      "findings", "referenced-claims"),
    M("findings.md", "- [verified] The middleware stack",
      "- The middleware stack", "findings", "assumption-untagged"),
    M("findings.md",
      "- [verified] The middleware stack wraps all public routes\n"
      "  (src/api/app.py:41).",
      "- [verified] The middleware stack wraps all public routes\n"
      "  everywhere, trust me.",
      "findings", "verified-unreferenced"),
    M("findings.md", "- [non-blocking] Should inbound",
      "- Should inbound", "findings", "question-untagged"),
    M("plan.md",
      [("1. Add RequestId middleware", "- Add RequestId middleware"),
       ("2. Bind the id", "- Bind the id"),
       ("3. Update header-set assertions", "- Update header-set assertions")],
      None, "plan", "steps-empty"),
    M("plan.md", "3. Update header-set assertions additively.\n"
      "   verify: pytest tests/api/test_headers.py",
      "3. Update header-set assertions additively.",
      "plan", "step-missing-verify"),
    M("ledger.md", "status: within-autonomy", "status: freestyle",
      "ledger", "ledger-format"),
    M("review.md", "undeclared_deviations: none", "no deviations, promise",
      "review", "fidelity-marker"),
    M("review.md", "## Verdict\napprove-with-fixes", "## Verdict\nship it",
      "review", "verdict-invalid"),
]


@pytest.mark.parametrize("mutation,expected,status", MATRIX)
def test_violation_matrix(task: Path, mutation, expected, status):
    file, old, new = mutation
    edit(task / file, old, new)
    report = validate.validate_task(task)
    assert not report.is_valid
    assert expected in fired(report), fired(report)
    assert report.artifacts[expected[0]].status == status


def test_verdict_fidelity_consistency(task: Path):
    edit(task / "review.md", "undeclared_deviations: none",
         "undeclared_deviations: found")
    edit(task / "review.md", "## Verdict\napprove-with-fixes",
         "## Verdict\napprove")
    report = validate.validate_task(task)
    assert ("review", "verdict-fidelity") in fired(report)


EXPRESS = next((ROOT / "tests" / "fixtures" / "express").iterdir())


@pytest.fixture()
def express_task(tmp_path: Path) -> Path:
    dst = tmp_path / EXPRESS.name
    shutil.copytree(EXPRESS, dst)
    return dst


def test_either_pin_set_is_accepted_but_never_a_mixture(express_task: Path,
                                                        task: Path):
    """D21: consumes_alt is a compatibility mechanism, not a licence.

    The validator is file-only — it cannot know a task's lane — so it accepts
    either complete shape and rejects anything in between. Whether a shape is
    *legal for this task* is the frontier's question, since only it reads the
    disposition."""
    assert validate.validate_task(express_task).is_valid   # alt set
    assert validate.validate_task(task).is_valid           # primary set

    # a mixture of the two sets satisfies neither
    edit(express_task / "review.md", "- artifact: request", "- artifact: intent")
    report = validate.validate_task(express_task)
    assert ("review", "consumes-set") in fired(report)
    message = next(v.message for v in report.all_violations()
                   if v.rule == "consumes-set")
    assert "or" in message      # both accepted shapes are named in the error

    # an artifact with no alternate set is unchanged: one shape, and the
    # error names one shape (the MATRIX covers findings' consumes-set case)
    assert schemas.SCHEMAS["findings"].consumes_alt is None
    edit(task / "findings.md", "- artifact: intent\n", "- artifact: plan\n")
    message = next(v.message for v in validate.validate_task(task)
                   .all_violations() if v.rule == "consumes-set")
    assert " or " not in message


def test_virtual_pins_are_git_refs_and_content_pins_are_not(task: Path):
    """D16: the two reference formats are not interchangeable.

    A real git tree id is 40 hex on a sha1 repository, so the old rule
    ('sha256:<64 hex>' for every pin) made every genuine review INVALID —
    the shape only a content hash can have. Each direction is now rejected.
    """
    ref = artifact.consumed_hashes(artifact.load(task / "review.md"))["diff"]
    assert ref.startswith(schemas.GIT_REF_PREFIX)

    # a content hash where a git object reference belongs
    edit(task / "review.md", ref, "sha256:" + "a" * 64)
    report = validate.validate_task(task)
    assert ("review", "hash-format") in fired(report)
    assert report.artifacts["review"].status == INVALID

    # and a git reference where a content hash belongs
    edit(task / "ledger.md", "- artifact: plan\n  hash: sha256:",
         "- artifact: plan\n  hash: git:")
    report = validate.validate_task(task)
    assert ("ledger", "hash-format") in fired(report)


def test_git_ref_accepts_both_object_formats(task: Path):
    """40 hex (sha1 repos, the default) and 64 hex (sha256 repos)."""
    ref = artifact.consumed_hashes(artifact.load(task / "review.md"))["diff"]
    for object_id in ("b" * 40, "c" * 64):
        copy = task / "review.md"
        edit(copy, ref, schemas.GIT_REF_PREFIX + object_id)
        report = validate.validate_task(copy.parent)
        assert ("review", "hash-format") not in fired(report)
        ref = schemas.GIT_REF_PREFIX + object_id


def test_unknown_artifact_is_task_level(task: Path):
    (task / "notes.md").write_text("---\n---\nscratch\n")
    report = validate.validate_task(task)
    assert ("<task>", "unknown-artifact") in fired(report)
    assert not report.is_valid


def test_upstream_missing(task: Path):
    (task / "findings.md").unlink()
    report = validate.validate_task(task)
    assert ("plan", "upstream-missing") in fired(report)
    assert report.artifacts["plan"].status == STALE


# --- staleness -------------------------------------------------------------

def test_stale_cascade_from_request_edit(task: Path):
    """Editing the immutable request marks the entire downstream chain

    stale (V3 request immutability is exactly this check on intent)."""
    edit(task / "request.md", "Probably a middleware?", "Definitely a middleware?")
    report = validate.validate_task(task)
    assert report.artifacts["request"].status == FRESH
    for downstream in ("intent", "findings", "plan", "ledger", "review"):
        assert report.artifacts[downstream].status == STALE, downstream
    assert not report.is_valid


def test_stale_cascade_transitive_through_unchanged_files(task: Path):
    """The blueprint's stale-cascade: editing intent.md directly stales

    findings and plan (they pin it), and ledger/review become stale
    transitively even though the plan's bytes never changed."""
    edit(task / "intent.md", "under a minute", "under two minutes")
    report = validate.validate_task(task)
    a = report.artifacts
    assert a["intent"].status == FRESH          # its own pins still match
    assert a["findings"].status == STALE        # direct pin mismatch
    assert a["plan"].status == STALE            # direct pin mismatch
    assert a["ledger"].status == STALE          # transitive via plan
    assert a["review"].status == STALE          # direct + transitive
    reasons = [v.message for v in a["ledger"].violations]
    assert any("itself stale" in m for m in reasons)


def test_invalid_upstream_makes_downstream_stale(task: Path):
    edit(task / "plan.md", "pipeline: 1", "pipeline: 42")
    report = validate.validate_task(task)
    assert report.artifacts["plan"].status == INVALID
    assert report.artifacts["ledger"].status == STALE


# --- purity and entry point ------------------------------------------------

def snapshot(d: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(d.glob("*"))}


def test_validator_is_pure(task: Path):
    before = snapshot(task)
    validate.validate_task(task)
    validate.validate_artifact(task / "review.md", task.name)
    assert snapshot(task) == before


def test_entrypoint_exit_codes(task: Path, capsys):
    assert validate.main([str(task)]) == 0
    edit(task / "intent.md", "## Non-goals", "## Non-goals-gone")
    assert validate.main([str(task)]) == 2
    assert validate.main([]) == 1
    out = capsys.readouterr().out
    assert '"is_valid": false' in out


def test_report_is_json_serializable(task: Path):
    import json
    edit(task / "review.md", "## Verdict\napprove-with-fixes", "## Verdict\nnope")
    json.dumps(validate.validate_task(task).to_dict())


def test_every_rule_id_is_covered():
    """The matrix (plus dedicated tests) exercises every rule in RULES."""
    covered = {p.values[1][1] for p in MATRIX}
    covered |= {"verdict-fidelity", "unknown-artifact", "upstream-missing", "stale"}
    assert covered == set(validate.RULES)


# --- registry graph invariants (structural architecture checks) ------------

def broken(**changes: schemas.Schema) -> dict[str, schemas.Schema]:
    reg = dict(schemas.SCHEMAS)
    reg.update(changes)
    return reg


def test_registry_rejects_two_producers():
    reg = broken(extra=replace(schemas.SCHEMAS["review"], artifact="extra"))
    with pytest.raises(SchemaError, match="more than one artifact"):
        schemas._check_registry(reg)


def test_registry_rejects_orphan_artifact():
    """A dangling artifact violates the graph invariants whichever check

    names it first (terminal uniqueness / reachability)."""
    reg = broken(orphan=schemas.Schema(
        artifact="orphan", produced_by="orphaning",
        frontmatter_fields=schemas.COMMON_FRONTMATTER,
        consumes_spec=(), required_sections=()))
    with pytest.raises(SchemaError, match="terminal|unreachable|root"):
        schemas._check_registry(reg)


def test_registry_rejects_second_root():
    reg = broken(seed=schemas.Schema(
        artifact="seed", produced_by=None,
        frontmatter_fields=("task",), consumes_spec=(),
        required_sections=()))
    with pytest.raises(SchemaError, match="exactly one root"):
        schemas._check_registry(reg)


def test_registry_rejects_second_terminal():
    reg = broken(audit=schemas.Schema(
        artifact="audit", produced_by="auditing",
        frontmatter_fields=schemas.COMMON_FRONTMATTER,
        consumes_spec=("review",), required_sections=()))
    # audit is consumed by nobody AND review stops being terminal-unique
    with pytest.raises(SchemaError, match="terminal"):
        schemas._check_registry(reg)


def test_registry_rejects_cycle():
    """A mid-chain cycle (findings <-> plan) that keeps root and terminal

    unique, so the DFS cycle detector is the invariant that fires."""
    reg = broken(findings=replace(
        schemas.SCHEMAS["findings"],
        consumes_spec=("request", "intent", "plan")))
    with pytest.raises(SchemaError, match="cycle"):
        schemas._check_registry(reg)


def test_registry_rejects_unknown_consume_edge():
    reg = broken(intent=replace(schemas.SCHEMAS["intent"],
                                consumes_spec=("request", "vibes")))
    with pytest.raises(SchemaError, match="unknown artifact"):
        schemas._check_registry(reg)


def test_real_registry_passes():
    schemas._check_registry()


# --- D28: artifact-authoring mechanics -------------------------------------
# Three ergonomics defects observed across six independent benchmark runs of
# the pipeline driving real work. Each cost a correction round; none was a
# question about the pipeline model.

def test_decorated_tags_are_accepted(task: Path):
    """`- **[verified]** …` must validate: the contract texts render the tags

    decorated, so a literal prefix match rejects a document that follows the
    documentation. The tag is the contract; its markdown styling is not."""
    f = task / "findings.md"
    text = f.read_text()
    assert "- [verified]" in text, "fixture no longer exercises the tag rule"
    f.write_text(text.replace("- [verified]", "- **[verified]**")
                     .replace("- [unverified]", "- **[unverified]**")
                     .replace("- [blocking]", "- **[blocking]**")
                     .replace("- [non-blocking]", "- **[non-blocking]**"))
    report = validate.validate_task(task)
    codes = {v.rule for v in report.all_violations()}
    assert not codes & {"assumption-untagged", "question-untagged"}, codes


def test_decorated_verdict_is_accepted(task: Path):
    """A backticked or bolded verdict token still resolves to the enum."""
    f = task / "review.md"
    text = f.read_text()
    assert "\napprove-with-fixes\n" in text, "fixture verdict anchor moved"
    for decorated in ("`approve-with-fixes`", "**approve-with-fixes**"):
        f.write_text(text.replace("\napprove-with-fixes\n", f"\n{decorated}\n"))
        report = validate.validate_task(task)
        codes = {v.rule for v in report.all_violations()}
        assert "verdict-invalid" not in codes, (decorated, codes)


def test_untagged_violation_names_the_expected_form(task: Path):
    """A violation an author cannot act on without reading validate.py is a

    defect in the message, not in the author."""
    f = task / "findings.md"
    f.write_text(f.read_text().replace("- [verified]", "- naked claim"))
    report = validate.validate_task(task)
    msgs = [v.message for v in report.all_violations()
            if v.rule == "assumption-untagged"]
    assert msgs, "expected the rule to fire"
    assert any("[verified]" in m for m in msgs), msgs
