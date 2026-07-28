"""M6 acceptance: the computed floor (D18).

The floor is what stops an agent lowering its own oversight, so the tests
here are mostly about its failure direction: every unknown must raise the
floor, never lower it. Also covers glob semantics (predictable, not
fnmatch's), purity, determinism, and the lane ordering Phase 3b enforces.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reins import cli, decisions as dec, floor as fl
from reins.schemas import LANES

POLICY = {
    "governed_paths": ["auth/**", "migrations/**", "*.toml", ".dev/config.yaml"],
    "max_files": 3,
    "max_lines": 100,
}


def facts(paths: list[str], lines: int | None = 10) -> dict:
    return {"changed_paths": paths, "lines_changed": lines}


# --- glob semantics --------------------------------------------------------

@pytest.mark.parametrize("path,pattern,expected", [
    # '**' spans whole segments
    ("auth/session.py", "auth/**", True),
    ("auth/deep/nested/x.py", "auth/**", True),
    ("auth", "auth/**", False),               # the directory itself is not inside it
    ("authorize.py", "auth/**", False),       # not a path-segment match
    # '*' stays inside one segment — the reason fnmatch is not used
    ("pyproject.toml", "*.toml", True),
    ("sub/pyproject.toml", "*.toml", False),
    ("sub/pyproject.toml", "**/*.toml", True),
    ("pyproject.toml", "**/*.toml", True),
    # '**' in the middle matches zero segments too
    ("a/b", "a/**/b", True),
    ("a/x/b", "a/**/b", True),
    ("a/x/y/b", "a/**/b", True),
    ("a/bb", "a/**/b", False),
    # '?' is one character, still segment-bound
    ("v1.py", "v?.py", True),
    ("a/v1.py", "v?.py", False),
    # literals are escaped, not treated as regex
    ("a.b.py", "a.b.py", True),
    ("axbxpy", "a.b.py", False),
])
def test_glob_semantics(path, pattern, expected):
    assert fl.matches(path, pattern) is expected


# --- the express path (the only way to get it) -----------------------------

def test_small_ungoverned_change_is_express():
    result = fl.compute(facts(["src/retry.py"], lines=4), POLICY)
    assert result["floor"] == "express"
    assert result["reasons"] == []
    assert result["basis"] == {
        "configured": True, "files": 1, "lines_changed": 4,
        "governed_matches": [],
        "limits": {"max_files": 3, "max_lines": 100},
    }


# --- every unknown raises the floor ---------------------------------------

@pytest.mark.parametrize("given_facts,config,reason_fragment", [
    # no policy at all: a fresh repo cannot judge anything small
    (facts(["src/retry.py"], 4), None, "no floor policy configured"),
    # nothing supplied: extent unknown
    (facts([], 4), POLICY, "no changed paths supplied"),
    # extent not measured
    (facts(["src/retry.py"], None), POLICY, "not measured"),
    # governed surfaces, however small the diff
    (facts(["auth/session.py"], 1), POLICY, "governed path auth/session.py"),
    (facts(["migrations/0007.sql"], 1), POLICY, "governed path"),
    (facts(["pyproject.toml"], 1), POLICY, "governed path pyproject.toml"),
    # the policy governs itself: moving the bar is never express work
    (facts([".dev/config.yaml"], 1), POLICY, "governed path .dev/config.yaml"),
    # extent limits
    (facts(["a.py", "b.py", "c.py", "d.py"], 4), POLICY, "4 files changed"),
    (facts(["a.py"], 900), POLICY, "900 lines changed"),
])
def test_unknowns_and_risks_raise_the_floor(given_facts, config, reason_fragment):
    result = fl.compute(given_facts, config)
    assert result["floor"] == "full"
    assert any(reason_fragment in r for r in result["reasons"]), result["reasons"]


def test_a_one_file_rewrite_is_not_express():
    """File count alone would call this small; line count is why it is not."""
    assert fl.compute(facts(["src/api.py"], 800), POLICY)["floor"] == "full"


def test_missing_limits_fall_back_to_conservative_defaults():
    result = fl.compute(facts(["a.py", "b.py", "c.py", "d.py"], 4),
                        {"governed_paths": []})
    assert result["basis"]["limits"] == {
        "max_files": fl.DEFAULT_MAX_FILES, "max_lines": fl.DEFAULT_MAX_LINES}
    assert result["floor"] == "full"


def test_empty_policy_block_is_configured_but_governs_nothing():
    """An empty 'floor:' block is a deliberate policy, unlike an absent one."""
    result = fl.compute(facts(["auth/session.py"], 4), {})
    assert result["basis"]["configured"] is True
    assert result["floor"] == "express"     # nothing is governed, so nothing fires


# --- purity, determinism, explainability ----------------------------------

def test_compute_is_pure_and_deterministic():
    given, config = facts(["b.py", "a.py"], 4), dict(POLICY)
    first = fl.compute(given, config)
    second = fl.compute(given, config)
    assert first == second
    assert given == facts(["b.py", "a.py"], 4)      # inputs untouched
    assert config == POLICY
    assert json.dumps(first, sort_keys=True)        # serializable, no objects


def test_every_full_floor_is_explained():
    result = fl.compute(facts(["auth/a.py", "b.py", "c.py", "d.py"], 900),
                        POLICY)
    assert result["floor"] == "full"
    # every independent cause is reported, not just the first one to fire
    assert len(result["reasons"]) == 3          # governed + files + lines
    assert result["basis"]["governed_matches"] == [
        {"path": "auth/a.py", "pattern": "auth/**"}]


# --- the ordering Phase 3b will enforce ------------------------------------

@pytest.mark.parametrize("lane,floor_,expected", [
    ("express", "express", True),
    ("full", "express", True),
    ("full", "full", True),
    ("express", "full", False),          # the case the whole design exists for
    ("turbo", "express", False),         # unknown names never satisfy a floor
    ("express", "turbo", False),
])
def test_at_or_above(lane, floor_, expected):
    assert fl.at_or_above(lane, floor_) is expected


def test_lanes_are_ordered_least_to_most_process():
    assert LANES == ("express", "full")
    assert fl.EXPRESS == LANES[0] and fl.FULL == LANES[-1]


# --- CLI ------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    assert cli.main(["--root", str(tmp_path), "init"]) == 0
    return tmp_path


def add_task(repo: Path, capsys) -> str:
    cli.main(["--root", str(repo), "task", "add", "--title", "floor probe",
              "--body", "b"])
    return capsys.readouterr().out.strip()


def test_cli_reads_paths_from_a_file_and_reports_json(repo: Path, capsys):
    task = add_task(repo, capsys)
    paths = repo / "paths.txt"
    paths.write_text("src/retry.py\n\n")        # blank lines ignored
    assert cli.main(["--root", str(repo), "floor", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "4", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["floor"] == "express"
    assert result["task"] == task


def test_cli_uses_the_shipped_policy_which_governs_manifests(repo: Path, capsys):
    """`pipeline init` writes a real policy, so a fresh repo is usable —

    and its governed list covers the surfaces where a one-line diff is
    most often not a one-line risk."""
    task = add_task(repo, capsys)
    paths = repo / "paths.txt"
    paths.write_text("pyproject.toml\n")
    assert cli.main(["--root", str(repo), "floor", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "1", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["floor"] == "full"
    assert result["basis"]["configured"] is True


@pytest.mark.parametrize("path", [
    "auth/session.py", "src/auth/session.py", "app/crypto/keys.go",
    "db/migrations/0007.sql", "packages/api/package.json",
    "services/web/Dockerfile", "internal/secrets/vault.go",
    "backend/requirements-dev.txt", ".github/workflows/ci.yml",
    ".dev/config.yaml",
])
def test_shipped_policy_governs_at_any_depth(path: str):
    """D25: a root-anchored pattern governs nothing in a repo that keeps

    code under src/, lib/, app/ or pkg/ — and a policy that silently matches
    nothing is worse than no policy, because it looks like a control while
    granting the cheap lane to (say) a session-token change. This is the
    fail-safe direction the floor exists to protect, so it is pinned."""
    from reins import miniyaml
    from reins.cli import DEFAULT_CONFIG
    policy = miniyaml.loads(DEFAULT_CONFIG)["floor"]
    assert any(fl.matches(path, g) for g in policy["governed_paths"]), path
    assert fl.compute(facts([path], 1), policy)["floor"] == "full"


def test_shipped_policy_still_lets_ordinary_source_through():
    """The counterweight: if everything is governed, express is inert."""
    from reins import miniyaml
    from reins.cli import DEFAULT_CONFIG
    policy = miniyaml.loads(DEFAULT_CONFIG)["floor"]
    for path in ("src/api/retry.py", "lib/format.ts", "docs/notes.md",
                 "tests/test_retry.py"):
        assert fl.compute(facts([path], 4), policy)["floor"] == "express", path


def test_disposition_below_the_floor_needs_a_recorded_reason(tmp_path: Path):
    """D20: the escape hatch exists — people route around a system that

    cannot be unblocked — but it is loud, reasoned, and countable, which is
    exactly what `bypass` was not."""
    ok = dec.make("disposition", "2026-01-01T00:00:00Z",
                  lane="full", floor="express")
    assert ok.data == {"lane": "full", "floor": "express"}

    with pytest.raises(dec.DecisionError, match="requires a non-empty"):
        dec.make("disposition", "2026-01-01T00:00:00Z",
                 lane="express", floor="full")
    with pytest.raises(dec.DecisionError, match="requires a non-empty"):
        dec.make("disposition", "2026-01-01T00:00:00Z",
                 lane="express", floor="full", override_reason="   ")

    override = dec.make("disposition", "2026-01-01T00:00:00Z",
                        lane="express", floor="full",
                        override_reason="vendored file, reviewed by hand")
    assert override.data["override_reason"]

    # a reason on a lane that is NOT below the floor is a modelling error
    with pytest.raises(dec.DecisionError, match="only for a lane below"):
        dec.make("disposition", "2026-01-01T00:00:00Z", lane="full",
                 floor="express", override_reason="not an override")
    with pytest.raises(dec.DecisionError, match="not in"):
        dec.make("disposition", "2026-01-01T00:00:00Z", lane="turbo",
                 floor="full")


def test_floor_check_catches_a_lane_violation(repo: Path, capsys):
    """The realized floor is the same function over what the diff turned

    out to be. Disposing `express` and then touching a governed surface is
    caught mechanically at the gate, not by a human noticing."""
    task = add_task(repo, capsys)
    paths = repo / "paths.txt"

    # no disposition recorded: `full` by default, which no floor can exceed
    paths.write_text("auth/session.py\n")
    assert cli.main(["--root", str(repo), "floor-check", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["lane"] == "full"

    # disposed express, then the work touched a governed path
    assert cli.main(["--root", str(repo), "decide", "disposition", task,
                     "--lane", "express", "--floor", "express"]) == 0
    assert cli.main(["--root", str(repo), "floor-check", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "1"]) == 2
    err = capsys.readouterr().err
    assert "LANE VIOLATION" in err and "auth/session.py" in err

    # the same disposition against work that stayed small is fine
    paths.write_text("src/retry.py\n")
    assert cli.main(["--root", str(repo), "floor-check", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "2"]) == 0


def test_a_recorded_override_actually_clears_the_gate(repo: Path, capsys):
    """An escape hatch that does not open is decorative, and people route

    around a system they cannot unblock. The override clears the gate — and
    is reported when it does, never silently green."""
    task = add_task(repo, capsys)
    paths = repo / "paths.txt"
    paths.write_text("auth/session.py\n")
    check = ["--root", str(repo), "floor-check", task,
             "--changed-paths-file", str(paths), "--lines-changed", "1"]

    assert cli.main(["--root", str(repo), "decide", "disposition", task,
                     "--lane", "express", "--floor", "express"]) == 0
    assert cli.main(check) == 2                       # violation, as it should

    assert cli.main(["--root", str(repo), "decide", "disposition", task,
                     "--lane", "express", "--floor", "full",
                     "--reason", "vendored constant, reviewed by hand"]) == 0
    capsys.readouterr()
    assert cli.main(check) == 0
    out = capsys.readouterr().out
    assert "BELOW realized floor" in out and "reviewed by hand" in out

    assert cli.main(check + ["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["override_reason"] == (
        "vendored constant, reviewed by hand")


def test_cli_floor_is_full_when_the_config_has_no_floor_block(repo: Path,
                                                             capsys):
    task = add_task(repo, capsys)
    (repo / ".dev" / "config.yaml").write_text("pipeline: 1\n")
    paths = repo / "paths.txt"
    paths.write_text("src/retry.py\n")
    assert cli.main(["--root", str(repo), "floor", task,
                     "--changed-paths-file", str(paths),
                     "--lines-changed", "1", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["floor"] == "full"
    assert result["basis"]["configured"] is False
