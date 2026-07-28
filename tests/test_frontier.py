"""M2 acceptance: every frontier status has a fixture; the frontier is a

pure, deterministic function of (artifacts, decisions) — byte-for-byte
identical output for identical inputs, independent of directory location;
consent is hash-pinned and voided by edits; precedence holds."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from reins import artifact, decisions as dec, frontier as fr

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


@pytest.fixture()
def task(tmp_path: Path) -> Path:
    dst = tmp_path / HAPPY.name
    shutil.copytree(HAPPY, dst)
    return dst


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"anchor missing in {path.name}: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def strip_to(task: Path, *keep: str) -> None:
    for p in task.glob("*.md"):
        if p.stem not in keep:
            p.unlink()


def no_decisions(task: Path) -> None:
    (task / dec.FILENAME).unlink()


def drop_verifications(task: Path) -> None:
    """Rewrite the log without verification records (the fixture ships one)."""
    kept = [line for line in (task / dec.FILENAME).read_text().splitlines()
            if line.strip() and json.loads(line)["type"] != "verification"]
    (task / dec.FILENAME).write_text("\n".join(kept) + "\n")


def verification(tree_ref: str, verdict: str = "pass", verifier: str = "tests",
                 minute: int = 50) -> dec.Decision:
    return dec.make("verification", f"2026-07-25T09:{minute}:00Z",
                    verifier=verifier, tool="pytest 9.1.1",
                    predicate="the plan's verifications pass", verdict=verdict,
                    tree_ref=tree_ref, evidence_hash="sha256:" + "b" * 64,
                    standard_touched=False)


def consent_all(task: Path) -> None:
    """Re-pin both consents to current file hashes (post-mutation)."""
    no_decisions(task)
    if (task / "intent.md").exists():
        dec.append(task, dec.make("intent_confirmed", "2026-07-25T10:00:00Z",
                                  intent_hash=artifact.sha256(task / "intent.md"),
                                  edited=False))
    if (task / "plan.md").exists():
        dec.append(task, dec.make("plan_approved", "2026-07-25T10:01:00Z",
                                  plan_hash=artifact.sha256(task / "plan.md"),
                                  edited=False))


# --- the state matrix ------------------------------------------------------

def test_state_AWAITING_MERGE(task: Path):
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("AWAITING_MERGE", None)
    assert f.detail["verdict"] == "approve-with-fixes"
    assert f.detail["verifiers"] == ["tests"]


def test_state_UNVERIFIED(task: Path):
    """D19: a complete, approved chain does not open the merge gate until a

    passing check covers the tree that was *reviewed*. Not a human stop —
    the runtime resolves it by running the checks and recording them."""
    tree = artifact.consumed_hashes(artifact.load(task / "review.md"))["diff"]

    drop_verifications(task)
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("UNVERIFIED", None)
    assert tree in f.reason
    assert f.status not in fr.HUMAN_STATUSES

    # a pass against a DIFFERENT tree does not count: the anchor is the point
    dec.append(task, verification("git:" + "9" * 40, minute=50))
    assert fr.frontier(task).status == "UNVERIFIED"

    # nor does a failure against the reviewed tree
    dec.append(task, verification(tree, verdict="fail", minute=51))
    f = fr.frontier(task)
    assert (f.status, f.detail["not_passing"]) == ("UNVERIFIED", ["tests"])

    # re-running that verifier to a pass clears it (latest per verifier wins)
    dec.append(task, verification(tree, verdict="pass", minute=52))
    assert fr.frontier(task).status == "AWAITING_MERGE"

    # and a second verifier that cannot reach a pass re-blocks
    dec.append(task, verification(tree, verdict="inconclusive",
                                  verifier="security", minute=53))
    f = fr.frontier(task)
    assert (f.status, f.detail["not_passing"]) == ("UNVERIFIED", ["security"])


def test_state_NEW(task: Path):
    strip_to(task, "request")
    no_decisions(task)
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("NEW", "intent")


def test_state_REFINING(task: Path):
    """Missing intent with a non-empty log (here: a consent whose pinned

    hash no longer matches anything) => not pristine => REFINING, not NEW."""
    strip_to(task, "request")
    no_decisions(task)
    dec.append(task, dec.make("intent_confirmed", "2026-07-25T10:00:00Z",
                              intent_hash="sha256:" + "0" * 64, edited=False))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("REFINING", "intent")


def test_state_AWAITING_INTENT_CONSENT(task: Path):
    strip_to(task, "request", "intent")
    no_decisions(task)
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("AWAITING_INTENT_CONSENT", None)


def test_state_RESEARCHING(task: Path):
    strip_to(task, "request", "intent")
    consent_all(task)
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("RESEARCHING", "findings")


def test_state_PLANNING(task: Path):
    strip_to(task, "request", "intent", "findings")
    consent_all(task)
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("PLANNING", "planning")


def test_state_AWAITING_PLAN_APPROVAL(task: Path):
    strip_to(task, "request", "intent", "findings", "plan")
    no_decisions(task)
    dec.append(task, dec.make("intent_confirmed", "2026-07-25T10:00:00Z",
                              intent_hash=artifact.sha256(task / "intent.md"),
                              edited=False))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("AWAITING_PLAN_APPROVAL", None)


def test_state_IMPLEMENTING(task: Path):
    strip_to(task, "request", "intent", "findings", "plan")
    f = fr.frontier(task)  # fixture consents already pin these hashes
    assert (f.status, f.next_contract) == ("IMPLEMENTING", "execution")


def test_state_REVIEWING(task: Path):
    strip_to(task, "request", "intent", "findings", "plan", "ledger")
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("REVIEWING", "review")


def test_state_INVALID(task: Path):
    edit(task / "review.md", "## Verdict\napprove-with-fixes",
         "## Verdict\nship it")
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("INVALID", None)
    assert "verdict-invalid" in f.reason


def test_state_STALE(task: Path):
    edit(task / "intent.md", "under a minute", "under two minutes")
    f = fr.frontier(task)
    assert f.status == "STALE"
    assert f.detail["first_stale"] == "findings"
    assert f.next_contract == "findings"
    assert f.detail["stale"] == ["findings", "plan", "ledger", "review"]


def test_state_BLOCKED(task: Path):
    strip_to(task, "request", "intent", "findings", "plan")
    dec.append(task, dec.make("escalation", "2026-07-25T11:00:00Z",
                              trigger_id="E2", from_contract="execution",
                              detail="new dependency 'uuid7' not in plan"))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("BLOCKED", None)
    assert f.detail["trigger"] == "E2"


def test_state_RETURNED_by_decision_and_clearing(task: Path):
    """NOTE: consent_all() resets decisions.jsonl entirely and re-appends

    only the two gate consents — which also erases the 'escalation' and
    'returned' decisions appended above. So by the time f2 is computed,
    RETURNED precedence (rank 6) no longer has any 'returned' decision to
    act on at all, and this exercises the ordinary chain-walk fallback
    once that's true — NOT D11's produced_at-vs-decision comparison. That
    mechanism is exercised by
    test_state_RETURNED_by_decision_only_clears_on_genuine_regeneration,
    where the returned decision stays in the log throughout."""
    strip_to(task, "request", "intent", "findings", "plan")
    dec.append(task, dec.make("escalation", "2026-07-25T11:00:00Z",
                              trigger_id="E1", from_contract="execution",
                              detail="assumption false"))
    dec.append(task, dec.make("returned", "2026-07-25T11:05:00Z",
                              to_contract="planning", trigger_id="E1",
                              reason="re-plan around real ingestion limits"))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("RETURNED", "planning")
    edit(task / "plan.md", "produced_at: 2026-07-25T09:20:00Z",
         "produced_at: 2026-07-25T11:30:00Z")
    consent_all(task)
    f2 = fr.frontier(task)
    assert (f2.status, f2.next_contract) == ("IMPLEMENTING", "execution")
    assert dec.read(task).latest("returned") is None


def test_state_RETURNED_by_decision_only_clears_on_genuine_regeneration(
        task: Path):
    """D26 regression (bugfix): the returned decision stays in the log

    throughout, so clearing is decided purely by D11's rule — the target
    artifact's produced_at compared lexically against the decision's ts —
    exactly the mechanism the test above does not reach.

    Before the fix: PyYAML auto-parses produced_at's ISO-8601-looking
    scalar into a datetime on load; str()'d, that's '... HH:MM:SS+00:00'
    (space, offset) rather than the decision log's '...THH:MM:SSZ'. The
    space byte sorts before 'T', so ANY same-day comparison came out
    'not yet produced' regardless of actual chronology — RETURNED could
    never clear same-day, which is the normal case for a return-then-fix
    cycle."""
    strip_to(task, "request", "intent", "findings", "plan")
    dec.append(task, dec.make("escalation", "2026-07-25T11:00:00Z",
                              trigger_id="E1", from_contract="execution",
                              detail="assumption false"))
    dec.append(task, dec.make("returned", "2026-07-25T11:05:00Z",
                              to_contract="planning", trigger_id="E1",
                              reason="re-plan around real ingestion limits"))
    assert fr.frontier(task).status == "RETURNED"

    # Same calendar day, but strictly BEFORE the routing decision (a stale
    # re-approval, not a real fix) — correctly stays RETURNED. Establishes
    # that the fix discriminates rather than always clearing.
    edit(task / "plan.md", "produced_at: 2026-07-25T09:20:00Z",
         "produced_at: 2026-07-25T11:00:00Z")
    dec.append(task, dec.make("plan_approved", "2026-07-25T11:01:00Z",
                              plan_hash=artifact.sha256(task / "plan.md"),
                              edited=True))
    assert fr.frontier(task).status == "RETURNED"

    # Same calendar day, strictly AFTER the decision — the case that was
    # broken. Clears, with the returned decision still present in the log.
    edit(task / "plan.md", "produced_at: 2026-07-25T11:00:00Z",
         "produced_at: 2026-07-25T11:30:00Z")
    dec.append(task, dec.make("plan_approved", "2026-07-25T11:31:00Z",
                              plan_hash=artifact.sha256(task / "plan.md"),
                              edited=True))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("IMPLEMENTING", "execution")
    assert dec.read(task).latest("returned") is not None


def test_state_RETURNED_by_review_verdict(task: Path):
    edit(task / "review.md", "## Verdict\napprove-with-fixes",
         "## Verdict\nreturn-to-implement")
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("RETURNED", "execution")
    assert f.detail["verdict"] == "return-to-implement"


def test_state_BYPASSED(task: Path):
    strip_to(task, "request")
    no_decisions(task)
    dec.append(task, dec.make("bypass", "2026-07-25T09:01:00Z",
                              request_hash=artifact.sha256(task / "request.md"),
                              reason="single-file fix"))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("BYPASSED", None)


def test_state_DONE(task: Path):
    dec.append(task, dec.make("merged", "2026-07-25T12:00:00Z",
                              commit="abc1234"))
    f = fr.frontier(task)
    assert (f.status, f.next_contract) == ("DONE", None)


def test_all_statuses_have_matrix_coverage():
    import inspect, sys
    mod = sys.modules[__name__]
    covered = {name[len("test_state_"):].split("_by_")[0].split("_and_")[0]
               for name, _ in inspect.getmembers(mod, inspect.isfunction)
               if name.startswith("test_state_")}
    assert covered == set(fr.STATUSES)


# --- the express lane (D21) ------------------------------------------------

EXPRESS = next((ROOT / "tests" / "fixtures" / "express").iterdir())


@pytest.fixture()
def express_task(tmp_path: Path) -> Path:
    dst = tmp_path / EXPRESS.name
    shutil.copytree(EXPRESS, dst)
    return dst


def test_express_lane_walks_its_own_chain(express_task: Path):
    """The lane parameterises the same walk; it does not fork it. Two

    artifacts and one human stop (merge), because intent.md and plan.md
    never exist and so gates 1 and 2 cannot fire."""
    f = fr.frontier(express_task)
    assert (f.status, f.next_contract) == ("AWAITING_MERGE", None)

    (express_task / "review.md").unlink()
    f = fr.frontier(express_task)
    assert (f.status, f.next_contract) == ("REVIEWING", "review")

    (express_task / "ledger.md").unlink()
    f = fr.frontier(express_task)
    assert (f.status, f.next_contract) == ("IMPLEMENTING", "execution")

    # never REFINING/RESEARCHING/PLANNING: those artifacts are not required
    assert not (express_task / "intent.md").exists()


def test_express_still_requires_verification(express_task: Path):
    """The always-on obligations are lane-independent: D19 applies here."""
    drop_verifications(express_task)
    assert fr.frontier(express_task).status == "UNVERIFIED"


def test_express_escalates_to_full_by_re_disposition(express_task: Path):
    """A change that outgrows the lane needs no new machinery: recording a

    `full` disposition makes the walk require the full chain, and the task
    resumes at the first artifact it never had."""
    dec.append(express_task, dec.make(
        "disposition", "2026-07-25T09:30:00Z", lane="full", floor="full"))
    f = fr.frontier(express_task)
    assert (f.status, f.next_contract) == ("REFINING", "intent")


# --- determinism & precedence ---------------------------------------------

def test_frontier_is_deterministic_and_location_independent(tmp_path: Path):
    a = tmp_path / "left" / HAPPY.name
    b = tmp_path / "very" / "different" / "depth" / HAPPY.name
    shutil.copytree(HAPPY, a)
    shutil.copytree(HAPPY, b)
    fa1, fa2, fb = fr.frontier(a), fr.frontier(a), fr.frontier(b)
    assert fa1.to_json() == fa2.to_json() == fb.to_json()
    assert "tmp" not in fa1.to_json()  # no absolute paths leak


def test_frontier_is_pure(task: Path):
    before = {p.name: p.read_bytes() for p in sorted(task.glob("*"))}
    fr.frontier(task)
    assert {p.name: p.read_bytes() for p in sorted(task.glob("*"))} == before


def test_consent_voided_by_edit(task: Path):
    """D3: editing an approved plan voids the approval and reopens gate 2

    (the edit also stales downstream; strip downstream to isolate)."""
    strip_to(task, "request", "intent", "findings", "plan")
    edit(task / "plan.md", "## Out of scope", "## Out of scope\n- One more thing.")
    f = fr.frontier(task)
    assert f.status == "AWAITING_PLAN_APPROVAL"


def test_precedence_invalid_beats_stale_and_gates(task: Path):
    edit(task / "intent.md", "under a minute", "under two minutes")  # stales chain
    edit(task / "review.md", "## Verdict\napprove-with-fixes", "## Verdict\nnope")
    f = fr.frontier(task)
    assert f.status == "INVALID"


def test_precedence_done_beats_stale(task: Path):
    dec.append(task, dec.make("merged", "2026-07-25T12:00:00Z", commit="abc"))
    edit(task / "intent.md", "under a minute", "under two minutes")
    assert fr.frontier(task).status == "DONE"


def test_precedence_stale_beats_blocked(task: Path):
    dec.append(task, dec.make("escalation", "2026-07-25T11:00:00Z",
                              trigger_id="E1", from_contract="execution",
                              detail="x"))
    edit(task / "intent.md", "under a minute", "under two minutes")
    assert fr.frontier(task).status == "STALE"


def test_corrupt_decision_line_warns_never_crashes(task: Path):
    with (task / dec.FILENAME).open("a") as fh:
        fh.write("{not json at all\n")
        fh.write('{"type": "party", "ts": "2026-07-25T12:00:00Z"}\n')
    f = fr.frontier(task)
    assert f.status == "AWAITING_MERGE"
    assert len(f.warnings) == 2
