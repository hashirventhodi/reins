"""D14 acceptance: follow-up harvesting has the same deterministic

guarantees as the rest of the pipeline — golden candidate set in defined
order, exact-match dedup with origin accumulation, deterministic
titles/bodies, byte-identical output across runs and locations, purity,
already-created awareness, and deterministic creation via --create."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline import cli, followups as fu

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    assert cli.main(["--root", str(tmp_path), "init"]) == 0
    dst = tmp_path / ".dev" / "tasks" / HAPPY.name
    shutil.copytree(HAPPY, dst)
    return tmp_path


def task_dir(repo: Path) -> Path:
    return repo / ".dev" / "tasks" / HAPPY.name


# --- golden harvest --------------------------------------------------------

def test_golden_candidate_set_and_order(repo: Path):
    """Chain order (intent -> findings -> ledger -> review), document

    order within each source. The fixture yields exactly: one deferred
    non-goal, one out-of-scope observation, zero ledger candidates
    (plan_impact: none), two review findings (should-fix, nit)."""
    result = fu.harvest(task_dir(repo))
    assert result["task"] == HAPPY.name
    got = [(c["origins"][0]["artifact"],
            c["origins"][0].get("severity")) for c in result["candidates"]]
    assert got == [("intent", None), ("findings", None),
                   ("review", "should-fix"), ("review", "nit")]
    titles = [c["title"] for c in result["candidates"]]
    assert titles[0].startswith("General log cleanup or restructuring")
    assert all(len(t) <= fu.TITLE_MAX + 1 for t in titles)  # +1 for ellipsis
    assert all(c["already_created"] is None for c in result["candidates"])


def test_non_deferred_non_goals_are_excluded(repo: Path):
    bodies = " ".join(c["body"] for c in fu.harvest(task_dir(repo))["candidates"])
    assert "Distributed tracing" not in bodies       # non-goal without /defer/i


def test_ledger_candidate_when_plan_impact_deferring(repo: Path):
    d = task_dir(repo)
    ledger = d / "ledger.md"
    ledger.write_text(ledger.read_text().replace(
        "plan_impact: none", "plan_impact: step 3 deferred to a follow-up"))
    cands = fu.harvest(d)["candidates"]
    ledger_cands = [c for c in cands
                    if c["origins"][0]["artifact"] == "ledger"]
    assert len(ledger_cands) == 1
    assert ledger_cands[0]["body"].startswith("Deferred consequence of step 2:")
    # order: ledger sits between findings and review
    arts = [c["origins"][0]["artifact"] for c in cands]
    assert arts == ["intent", "findings", "ledger", "review", "review"]


# --- dedup -----------------------------------------------------------------

def test_dedup_exact_normalized_first_wins_origins_accumulate(repo: Path):
    d = task_dir(repo)
    intent = d / "intent.md"
    dup = ("- Logging   configuration is duplicated between app startup and "
           "worker\n  startup (src/api/logging.py:17, src/worker/boot.py:9) — "
           "cleanup\n  candidate, deferred per intent non-goals.")
    # place the duplicate inside Non-goals so it harvests (contains "deferred")
    intent.write_text(intent.read_text().replace(
        "- Distributed tracing across services.",
        f"- Distributed tracing across services.\n{dup}"))
    cands = fu.harvest(d)["candidates"]
    matches = [c for c in cands if "duplicated between app startup" in c["body"]]
    assert len(matches) == 1                       # exact-normalized dedup
    origins = matches[0]["origins"]
    assert [o["artifact"] for o in origins] == ["intent", "findings"]
    # first occurrence in chain order wins the body verbatim
    assert "Logging   configuration" in matches[0]["body"]


# --- determinism & purity --------------------------------------------------

def test_harvest_is_deterministic_and_location_independent(repo, tmp_path):
    other = tmp_path / "elsewhere"
    assert cli.main(["--root", str(other), "init"]) == 0
    shutil.copytree(task_dir(repo), other / ".dev" / "tasks" / HAPPY.name)
    j = lambda d: json.dumps(fu.harvest(d), sort_keys=True)
    assert j(task_dir(repo)) == j(task_dir(repo))
    assert j(task_dir(repo)) == j(other / ".dev" / "tasks" / HAPPY.name)
    assert "tmp" not in j(task_dir(repo))


def test_harvest_is_pure(repo: Path):
    d = task_dir(repo)
    before = {p.name: p.read_bytes() for p in sorted(d.glob("*"))}
    fu.harvest(d)
    assert {p.name: p.read_bytes() for p in sorted(d.glob("*"))} == before


def test_partial_chain_harvests_what_exists(repo: Path):
    d = task_dir(repo)
    (d / "review.md").unlink()
    (d / "ledger.md").unlink()
    arts = [c["origins"][0]["artifact"] for c in fu.harvest(d)["candidates"]]
    assert arts == ["intent", "findings"]


# --- creation (runtime-owned) & already_created ----------------------------

def create_via_runtime_flow(repo: Path, capsys, index: int) -> str:
    """Simulate the runtime: mechanical extraction from harvest JSON,

    then the task-add primitive with the normative creation body."""
    cand = fu.harvest(repo / ".dev" / "tasks" / HAPPY.name)["candidates"][index - 1]
    body_file = repo / f"cand{index}.md"
    body_file.write_text(fu.creation_body(cand, HAPPY.name))
    assert cli.main(["--root", str(repo), "task", "add",
                     "--title", cand["title"],
                     "--body-file", str(body_file),
                     "--source-ref", f"followup:{HAPPY.name}"]) == 0
    return capsys.readouterr().out.strip().splitlines()[-1]


def test_runtime_creation_flow_yields_lineage_and_already_created(repo, capsys):
    child_id = create_via_runtime_flow(repo, capsys, 2)
    raw = (repo / ".dev" / "tasks" / child_id / "request.md").read_text()
    assert f"source_ref: followup:{HAPPY.name}" in raw
    assert f"Origin: review of {HAPPY.name}" in raw
    cand2 = fu.harvest(repo / ".dev" / "tasks" / HAPPY.name)["candidates"][1]
    assert cand2["body"] in raw                    # verbatim body preserved
    assert cand2["already_created"] == child_id    # re-harvest sees the child


def test_slug_collision_backstops_duplicate_creation(repo, capsys):
    """Runtime-side skip is the primary duplicate guard (already_created

    in the JSON); the same-day title slug collision in task add is the
    deterministic backstop if a runtime misbehaves."""
    create_via_runtime_flow(repo, capsys, 2)
    cand = fu.harvest(repo / ".dev" / "tasks" / HAPPY.name)["candidates"][1]
    body_file = repo / "dup.md"
    body_file.write_text(fu.creation_body(cand, HAPPY.name))
    assert cli.main(["--root", str(repo), "task", "add",
                     "--title", cand["title"],
                     "--body-file", str(body_file),
                     "--source-ref", f"followup:{HAPPY.name}"]) == 1
    assert "collision" in capsys.readouterr().err


def test_followup_child_flows_into_telemetry_lineage(repo: Path, capsys):
    """Query 6's premise: a created follow-up's task_ref carries the

    followup: convention end to end."""
    child_id = create_via_runtime_flow(repo, capsys, 1)
    root = ["--root", str(repo)]
    cli.main([*root, "decide", "merged", child_id, "--commit", "beefcafe"])
    capsys.readouterr()
    cli.main([*root, "extract", child_id])
    record = json.loads(capsys.readouterr().out)
    assert record["task_ref"] == f"followup:{HAPPY.name}"
    assert record["outcome"] == "merged:beefcafe"


def test_already_created_survives_headings_in_body(repo: Path, capsys):
    """F4 regression guard: a follow-up body containing an '## ' line

    must still be matched by already-created detection (full body
    reconstruction, not preamble-only)."""
    d = task_dir(repo)
    findings = d / "findings.md"
    findings.write_text(findings.read_text().replace(
        "- Logging configuration is duplicated",
        "- Consider a docs page with an ## Overview heading for ops.\n"
        "- Logging configuration is duplicated"))
    cand = fu.harvest(d)["candidates"][1]
    assert "## Overview" in cand["body"]
    body_file = repo / "h.md"
    body_file.write_text(fu.creation_body(cand, HAPPY.name))
    assert cli.main(["--root", str(repo), "task", "add",
                     "--title", cand["title"], "--body-file", str(body_file),
                     "--source-ref", f"followup:{HAPPY.name}"]) == 0
    child_id = capsys.readouterr().out.strip().splitlines()[-1]
    recheck = fu.harvest(d)["candidates"][1]
    assert recheck["already_created"] == child_id
