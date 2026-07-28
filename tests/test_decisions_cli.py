"""M2: decisions log unit tests, CLI contract tests, and the mock-agent

end-to-end — a non-AI producer drives a task NEW -> AWAITING_MERGE with
exactly two consent commands, proving the state machine is runtime- and
model-independent (blueprint §12)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from reins import artifact, cli, decisions as dec, frontier as fr
from reins.schemas import PIPELINE_VERSION

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


# --- decisions.py ----------------------------------------------------------

def test_append_then_read_roundtrip(tmp_path: Path):
    d1 = dec.make("intent_confirmed", "2026-07-25T09:00:00Z",
                  intent_hash="sha256:" + "a" * 64, edited=False)
    d2 = dec.make("merged", "2026-07-25T10:00:00Z", commit="deadbee")
    dec.append(tmp_path, d1)
    dec.append(tmp_path, d2)
    log = dec.read(tmp_path)
    assert [x.to_dict() for x in log.decisions] == [d1.to_dict(), d2.to_dict()]
    assert log.warnings == []
    assert log.latest("merged").data["commit"] == "deadbee"


# A well-formed verification record (D17); cases below mutate one field each.
VERIFICATION = dict(
    verifier="tests", tool="pytest 9.1.1", predicate="the suite passes",
    verdict="pass", tree_ref="git:" + "a" * 40,
    evidence_hash="sha256:" + "b" * 64, standard_touched=False,
)


@pytest.mark.parametrize("kwargs,match", [
    (dict(dtype="vibes", ts="2026-01-01T00:00:00Z"), "unknown decision type"),
    (dict(dtype="merged", ts="yesterday", commit="c"), "ISO-8601"),
    (dict(dtype="merged", ts="2026-01-01T00:00:00Z"), "missing fields"),
    (dict(dtype="merged", ts="2026-01-01T00:00:00Z", commit="c",
          extra="nope"), "unexpected fields"),
    (dict(dtype="intent_confirmed", ts="2026-01-01T00:00:00Z",
          intent_hash="md5:x", edited=True), "sha256"),
    (dict(dtype="intent_confirmed", ts="2026-01-01T00:00:00Z",
          intent_hash="sha256:" + "a" * 64, edited="yes"), "boolean"),
    (dict(dtype="escalation", ts="2026-01-01T00:00:00Z", trigger_id="E9",
          from_contract="execution", detail="x"), "trigger_id"),
    (dict(dtype="returned", ts="2026-01-01T00:00:00Z", to_contract="magic",
          reason="r"), "to_contract"),
    (dict(dtype="returned", ts="2026-01-01T00:00:00Z", to_contract="planning",
          reason="r", verdict="lgtm"), "verdict"),
    # verification (D17): every field of the public contract is checked
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "verifier": "Security Scan"}), "lowercase slug"),
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "verdict": "green"}), "verdict"),
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "standard_touched": "yes"}), "boolean"),
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "tool": "  "}), "non-empty string"),
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "predicate": ""}), "non-empty string"),
    # a content hash where a git object reference belongs, and vice versa
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "tree_ref": "sha256:" + "a" * 64}), "git:<object id>"),
    (dict(dtype="verification", ts="2026-01-01T00:00:00Z", **{
        **VERIFICATION, "evidence_hash": "git:" + "a" * 40}), "sha256"),
])
def test_append_is_strict(tmp_path: Path, kwargs, match):
    dtype = kwargs.pop("dtype")
    ts = kwargs.pop("ts")
    with pytest.raises(dec.DecisionError, match=match):
        dec.make(dtype, ts, **kwargs)
    assert not (tmp_path / dec.FILENAME).exists()  # strict append: no write


def test_read_is_tolerant(tmp_path: Path):
    good = dec.make("merged", "2026-01-01T00:00:00Z", commit="c")
    dec.append(tmp_path, good)
    with (tmp_path / dec.FILENAME).open("a") as fh:
        fh.write("garbage\n")
    log = dec.read(tmp_path)
    assert len(log.decisions) == 1 and len(log.warnings) == 1


def test_module_exposes_no_rewrite():
    assert not any(n for n in dir(dec)
                   if "delete" in n.lower() or "rewrite" in n.lower())


# --- CLI -------------------------------------------------------------------

def run(*argv: str) -> int:
    return cli.main(list(argv))


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    assert run("--root", str(tmp_path), "init") == 0
    return tmp_path


def test_init_idempotent(repo: Path):
    assert run("--root", str(repo), "init") == 0
    assert (repo / ".dev" / "tasks").is_dir()
    assert (repo / "telemetry.jsonl").exists()


def test_task_add_is_byte_exact(repo: Path, capsys):
    body = "Fix the thing.\r\nWith trailing space   \nand no final newline"
    src = repo / "issue.txt"
    src.write_bytes(body.encode())
    assert run("--root", str(repo), "task", "add", "--title",
               "Fix the thing!", "--body-file", str(src),
               "--source-ref", "gh:123") == 0
    task_id = capsys.readouterr().out.strip()
    raw = (repo / ".dev" / "tasks" / task_id / "request.md").read_bytes()
    assert raw.endswith(body.encode())          # verbatim, byte-exact
    assert b"source_ref: gh:123" in raw
    a = artifact.load(repo / ".dev" / "tasks" / task_id / "request.md")
    assert a.frontmatter["task"] == task_id


def test_task_add_collision(repo: Path, capsys):
    assert run("--root", str(repo), "task", "add", "--title", "same title",
               "--body", "x") == 0
    capsys.readouterr()
    assert run("--root", str(repo), "task", "add", "--title", "same title",
               "--body", "y") == 1
    assert "collision" in capsys.readouterr().err


def test_usage_exit_code():
    assert run("definitely-not-a-command") == 1
    assert run("status", "no-such-task") == 1


def test_consent_refused_on_invalid_artifact(repo: Path, capsys):
    run("--root", str(repo), "task", "add", "--title", "t", "--body", "b")
    task_id = capsys.readouterr().out.strip()
    d = repo / ".dev" / "tasks" / task_id
    (d / "intent.md").write_text("---\npipeline: 1\n---\n## Wrong\nx\n")
    assert run("--root", str(repo), "consent", "intent", task_id) == 2


# --- the mock-agent end-to-end (M2 acceptance) -----------------------------

TEMPLATES = {name: artifact.load(HAPPY / f"{name}.md")
             for name in ("intent", "findings", "plan", "ledger", "review")}
# The diff pin is a git object reference (D16), taken from the executable
# spec so there is exactly one place a real one is derived.
DIFF_REF = artifact.consumed_hashes(TEMPLATES["review"])["diff"]


def mock_agent_produce(repo: Path, task_id: str, contract: str,
                       minute: int) -> None:
    """A shell-script-grade producer: copies the canned body for the

    contract's artifact and wires frontmatter exclusively through the CLI
    (models must never hand-compute hashes — R2)."""
    produced = {"intent": "intent", "findings": "findings",
                "planning": "plan", "execution": "ledger",
                "review": "review"}[contract]
    d = repo / ".dev" / "tasks" / task_id
    template = TEMPLATES[produced]
    out = artifact.Artifact(path=str(d / f"{produced}.md"), frontmatter={},
                            preamble=template.preamble,
                            sections=dict(template.sections))
    artifact.dump(out, d / f"{produced}.md")
    sets = [f"pipeline={PIPELINE_VERSION}", f"contract={contract}",
            f"task={task_id}", f"produced_at=2026-07-25T10:{minute:02d}:00Z"]
    args = ["frontmatter", str(d / f"{produced}.md")]
    for s in sets:
        args += ["--set", s]
    for upstream in {"intent": ["request"], "findings": ["request", "intent"],
                     "plan": ["intent", "findings"], "ledger": ["plan"],
                     "review": ["intent", "plan", "ledger"]}[produced]:
        args += ["--pin", f"{upstream}={d / f'{upstream}.md'}"]
    if produced == "review":
        args += ["--pin", f"diff={DIFF_REF}"]
    assert run(*args) == 0


def test_mock_agent_end_to_end(repo: Path, capsys):
    """NEW -> AWAITING_MERGE with zero human file edits and exactly two

    consent commands; then merge -> DONE. Every transition is asserted."""
    run("--root", str(repo), "task", "add", "--title",
        "request id tracing", "--body", "Add a request id header.")
    task_id = capsys.readouterr().out.strip()
    root = ["--root", str(repo)]

    def status() -> fr.Frontier:
        return fr.frontier(repo / ".dev" / "tasks" / task_id)

    assert status().status == "NEW"
    mock_agent_produce(repo, task_id, "intent", 1)
    assert status().status == "AWAITING_INTENT_CONSENT"
    assert run(*root, "status", task_id) == 3            # needs-human exit
    assert run(*root, "consent", "intent", task_id) == 0  # human act #1
    assert status().status == "RESEARCHING"
    mock_agent_produce(repo, task_id, "findings", 2)
    assert status().status == "PLANNING"
    mock_agent_produce(repo, task_id, "planning", 3)
    assert status().status == "AWAITING_PLAN_APPROVAL"
    assert run(*root, "consent", "plan", task_id) == 0    # human act #2
    assert status().status == "IMPLEMENTING"
    mock_agent_produce(repo, task_id, "execution", 4)
    assert status().status == "REVIEWING"
    mock_agent_produce(repo, task_id, "review", 5)
    # D19: reviewed but not yet verified — the runtime resolves this itself
    assert status().status == "UNVERIFIED"
    evidence = repo / "verify-out.txt"
    evidence.write_bytes(b"3 passed\n")
    assert run(*root, "verify", task_id, "--verifier", "tests",
               "--tool", "pytest 9.1.1", "--predicate", "AC1-AC3 pass",
               "--verdict", "pass", "--tree-ref", DIFF_REF,
               "--evidence-file", str(evidence)) == 0
    f = status()
    assert (f.status, f.detail["verdict"]) == ("AWAITING_MERGE",
                                               "approve-with-fixes")
    assert run(*root, "validate", task_id) == 0
    assert run(*root, "next", task_id) == 3
    assert run(*root, "decide", "merged", task_id, "--commit", "cafe123") == 0
    assert status().status == "DONE"


def test_mock_agent_escalation_path(repo: Path, capsys):
    """IMPLEMENTING -> BLOCKED (E2) -> human routes -> RETURNED(planning)."""
    run("--root", str(repo), "task", "add", "--title", "esc", "--body", "b")
    task_id = capsys.readouterr().out.strip()
    root = ["--root", str(repo)]
    mock_agent_produce(repo, task_id, "intent", 1)
    run(*root, "consent", "intent", task_id)
    mock_agent_produce(repo, task_id, "findings", 2)
    mock_agent_produce(repo, task_id, "planning", 3)
    run(*root, "consent", "plan", task_id)
    assert run(*root, "decide", "escalation", task_id, "--trigger", "E2",
               "--from", "execution", "--detail", "new dep not in plan") == 0
    d = repo / ".dev" / "tasks" / task_id
    assert fr.frontier(d).status == "BLOCKED"
    assert run(*root, "status", task_id) == 3
    assert run(*root, "decide", "returned", task_id, "--to", "planning",
               "--reason", "re-plan with the dependency named") == 0
    f = fr.frontier(d)
    assert (f.status, f.next_contract) == ("RETURNED", "planning")


def test_bypass_cannot_be_created_but_stays_readable(repo: Path, capsys):
    """D22: the express lane replaced bypass, so there is no longer a way to

    create one — but decisions are append-only history, and a log written
    before the change must still resolve. Creation retired, reader kept."""
    run("--root", str(repo), "task", "add", "--title", "tiny", "--body", "b")
    task_id = capsys.readouterr().out.strip()
    d = repo / ".dev" / "tasks" / task_id

    assert run("--root", str(repo), "decide", "bypass", task_id,
               "--reason", "single-file fix") == 1        # usage error: gone

    # a historical record, written directly, still resolves to BYPASSED
    dec.append(d, dec.make("bypass", "2026-07-25T09:01:00Z",
                           request_hash=artifact.sha256(d / "request.md"),
                           reason="recorded before D22"))
    assert fr.frontier(d).status == "BYPASSED"


def _add_task(repo: Path, capsys) -> str:
    run("--root", str(repo), "task", "add", "--title", "verify probe",
        "--body", "b")
    return capsys.readouterr().out.strip()


def test_verify_records_a_result_and_hashes_the_evidence(repo: Path, capsys):
    """D17: the runtime runs the check and supplies its judgment; the product

    records it and hashes the captured output so no caller hand-writes a
    hash (R2). Nothing is executed by the product."""
    task_id = _add_task(repo, capsys)
    evidence = repo / "out.txt"
    evidence.write_bytes(b"3 passed\n")
    assert run("--root", str(repo), "verify", task_id,
               "--verifier", "tests", "--tool", "pytest 9.1.1",
               "--predicate", "the suite passes", "--verdict", "pass",
               "--tree-ref", "git:" + "c" * 40,
               "--evidence-file", str(evidence)) == 0

    record = dec.read(repo / ".dev" / "tasks" / task_id).latest("verification")
    assert record.data["evidence_hash"] == artifact.sha256(evidence)
    assert record.data["verdict"] == "pass"
    assert record.data["standard_touched"] is False


def test_verify_rejects_ambiguous_evidence(repo: Path, capsys):
    task_id = _add_task(repo, capsys)
    for extra in ([], ["--evidence-file", "x", "--evidence-hash",
                       "sha256:" + "a" * 64]):
        assert run("--root", str(repo), "verify", task_id,
                   "--verifier", "tests", "--tool", "t",
                   "--predicate", "p", "--verdict", "pass",
                   "--tree-ref", "git:" + "c" * 40, *extra) == 1


def test_verification_is_required_at_the_merge_gate(repo: Path, capsys):
    """D19 (was: "…is_not_yet_required", inverted deliberately in Phase 3a).

    A complete, approved chain now stops at UNVERIFIED until a passing check
    covers the reviewed tree. UNVERIFIED is not a human stop: `pipeline
    verify` resolves it, so the exit code stays 0."""
    task_id = _add_task(repo, capsys)
    d = repo / ".dev" / "tasks" / task_id
    for minute, contract in enumerate(
            ("intent", "findings", "planning", "execution", "review"), 1):
        mock_agent_produce(repo, task_id, contract, minute)
        if contract == "intent":
            run("--root", str(repo), "consent", "intent", task_id)
        if contract == "planning":
            run("--root", str(repo), "consent", "plan", task_id)
    assert dec.read(d).latest("verification") is None
    assert fr.frontier(d).status == "UNVERIFIED"
    assert run("--root", str(repo), "status", task_id) == 0   # not a human stop

    evidence = repo / "out.txt"
    evidence.write_bytes(b"3 passed\n")
    assert run("--root", str(repo), "verify", task_id,
               "--verifier", "tests", "--tool", "pytest 9.1.1",
               "--predicate", "the plan's verifications pass",
               "--verdict", "pass", "--tree-ref", DIFF_REF,
               "--evidence-file", str(evidence)) == 0
    assert fr.frontier(d).status == "AWAITING_MERGE"


def test_status_json_matches_frontier(repo: Path, capsys):
    run("--root", str(repo), "task", "add", "--title", "j", "--body", "b")
    task_id = capsys.readouterr().out.strip()
    run("--root", str(repo), "status", task_id, "--json")
    out = json.loads(capsys.readouterr().out)
    assert out == fr.frontier(repo / ".dev" / "tasks" / task_id).to_dict()


# --- D28: frontmatter can bootstrap its own fence --------------------------

def test_frontmatter_init_creates_the_fence(tmp_path):
    """The contracts say: write the artifact body, then set frontmatter only

    through this command. It could not bootstrap the fence it required, so
    every artifact in every observed run cost a failed invocation plus a
    hand-written fence — in the one command that exists to keep hands off
    frontmatter."""
    from reins import cli
    f = tmp_path / "intent.md"
    f.write_text("# Intent\n\nbody\n", encoding="utf-8")
    assert cli.main(["frontmatter", str(f), "--init", "--set", "pipeline=1"]) == 0
    text = f.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "pipeline: 1" in text
    assert "# Intent" in text and "body" in text  # body preserved verbatim


def test_frontmatter_without_init_still_refuses_but_names_the_fix(tmp_path, capsys):
    """Backward compatible: the old failure stands, now self-diagnosing."""
    from reins import cli
    f = tmp_path / "intent.md"
    f.write_text("# Intent\n", encoding="utf-8")
    assert cli.main(["frontmatter", str(f), "--set", "pipeline=1"]) != 0
    assert "--init" in capsys.readouterr().err


# --- task reference resolution (D37) ---------------------------------

def _seed_tasks(tmp_path, titles):
    ids = []
    for t in titles:
        out = io.StringIO()
        with redirect_stdout(out):
            assert run("--root", str(tmp_path), "task", "add", "--title", t,
                       "--body", "b") == 0
        ids.append(out.getvalue().strip())
    return ids


def test_exact_task_id_still_resolves(tmp_path):
    """Backward compatibility: nothing that worked before may break."""
    (full,) = _seed_tasks(tmp_path, ["add a request id header"])
    assert run("--root", str(tmp_path), "status", full) in (0, 2, 3)


def test_a_fragment_resolves_when_unambiguous(tmp_path):
    """The point of D37: the id is long and its noisy part (the date)
    comes first, so a substring — not a prefix — is what a human types."""
    (full,) = _seed_tasks(tmp_path, ["add a request id header"])
    for fragment in ("request-id", "REQUEST-ID", "header", "add-a-request"):
        out = io.StringIO()
        with redirect_stdout(out):
            run("--root", str(tmp_path), "status", fragment, "--json")
        assert json.loads(out.getvalue())["task"] == full, fragment


def test_ambiguous_fragment_refuses_and_lists_candidates(tmp_path, capsys):
    """Acting on the wrong task costs more than the keystrokes saved, so
    ambiguity errors rather than guessing."""
    ids = _seed_tasks(tmp_path, ["retry the upload path",
                                 "retry the download path"])
    assert run("--root", str(tmp_path), "status", "retry") == 1
    err = capsys.readouterr().err
    assert "ambiguous" in err
    for i in ids:                      # every candidate is named
        assert i in err


def test_unknown_fragment_is_a_usage_error(tmp_path, capsys):
    _seed_tasks(tmp_path, ["add a request id header"])
    assert run("--root", str(tmp_path), "status", "nonexistent") == 1
    assert "no such task" in capsys.readouterr().err
