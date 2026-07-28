"""M5 acceptance — packaging and verification only, no new logic:

  A1 clean install onto a fresh (simulated) machine via documented steps;
  A2 migration of an existing repo + rollback leaving zero residue
     (byte-identical tree);
  A3 a complete happy-path task, intake -> telemetry, using ONLY public
     interfaces (the `reins_cli.py` entry point via subprocess — no
     in-process imports drive the flow);
  A4 dependency audit: product imports are stdlib only (D30), and the
     runtime -> pipeline direction never reverses."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())
ENTRY = ROOT / "reins_cli.py"
PIPE = [sys.executable, str(ENTRY)]


def sh(args: list[str], cwd: Path, check: bool = True,
       env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(env_extra or {})  # the entry point self-locates (D30)
    proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                          text=True)
    if check:
        assert proc.returncode == 0, f"{args}: {proc.stderr}\n{proc.stdout}"
    return proc


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# --- A1: fresh-machine install ---------------------------------------------

def test_A1_clean_install_documented_steps_only(tmp_path: Path):
    home = tmp_path / "fresh-home"
    sh(["sh", str(ROOT / "install.sh")], cwd=ROOT,
       env_extra={"CLAUDE_HOME": str(home / ".claude")})
    # everything the doc promises, nothing else at top level
    claude = home / ".claude"
    assert sorted(p.name for p in claude.iterdir()) == [
        "agents", "commands", "reins", "skills"]
    assert (claude / "reins" / "contracts" / "intent.md").exists()
    # the core runs by path through the installed symlink, no PATH entry
    core_entry = claude / "reins" / "core" / "reins_cli.py"
    assert core_entry.exists()
    proc = sh([sys.executable, str(core_entry), "--help"], cwd=tmp_path,
              check=False)
    assert proc.returncode in (0, 1)  # argparse help exits 0
    assert "task" in proc.stdout + proc.stderr


# --- A2 + A3: migration, public-interface happy path, rollback -------------

def make_legacy_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("print('legacy')\n")
    (root / "AGENTS.md").write_text("# Agent notes\n## Pitfalls\n- none yet\n")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    (root / ".gitignore").write_text("*.pyc\n")


def mock_produce(repo: Path, task_id: str, contract: str, minute: int) -> None:
    """Public-interface producer: writes the canned body, then wires ALL

    frontmatter through the `reins_cli.py frontmatter` entry point."""
    from reins import artifact  # test harness only reads templates
    produced = {"intent": "intent", "findings": "findings",
                "planning": "plan", "execution": "ledger",
                "review": "review"}[contract]
    d = repo / ".dev" / "tasks" / task_id
    template = artifact.load(HAPPY / f"{produced}.md")
    out = artifact.Artifact(path="", frontmatter={},
                            preamble=template.preamble,
                            sections=dict(template.sections))
    artifact.dump(out, d / f"{produced}.md")
    args = [*PIPE, "frontmatter", str(d / f"{produced}.md"),
            "--set", "pipeline=1", "--set", f"contract={contract}",
            "--set", f"task={task_id}",
            "--set", f"produced_at=2026-07-25T10:{minute:02d}:00Z"]
    pins = {"intent": ["request"], "findings": ["request", "intent"],
            "plan": ["intent", "findings"], "ledger": ["plan"],
            "review": ["intent", "plan", "ledger"]}[produced]
    for upstream in pins:
        args += ["--pin", f"{upstream}={d / f'{upstream}.md'}"]
    if produced == "review":
        # a git object reference, not a content hash (D16); taken from the
        # executable spec, where the only real derivation lives
        diff_ref = artifact.consumed_hashes(
            artifact.load(HAPPY / "review.md"))["diff"]
        args += ["--pin", f"diff={diff_ref}"]
    sh(args, cwd=repo)


def test_A2_A3_migration_happy_path_and_rollback(tmp_path: Path):
    repo = tmp_path / "legacy"
    repo.mkdir()
    make_legacy_repo(repo)
    before = tree_snapshot(repo)

    # --- migration, exactly the documented steps (docs/migration.md §2)
    sh([*PIPE, "init"], cwd=repo)
    (repo / ".claude" / "hooks").mkdir(parents=True)
    for hook in (ROOT / "runtime" / "claude" / "hooks").glob("*.sh"):
        (repo / ".claude" / "hooks" / hook.name).write_bytes(hook.read_bytes())
    (repo / ".claude" / "settings.json").write_bytes(
        (ROOT / "runtime" / "claude" / "settings.example.json").read_bytes())
    with (repo / ".gitignore").open("a") as fh:
        fh.write(".claude/settings.local.json\n")

    # --- A3: full happy path via the executable only
    def status() -> dict:
        proc = sh([*PIPE, "status", "T", "--json"], cwd=repo, check=False)
        return json.loads(proc.stdout)

    proc = sh([*PIPE, "task", "add", "--title", "request id tracing",
               "--body", "Add a request id header.",
               "--source-ref", "gh:123"], cwd=repo)
    task_id = proc.stdout.strip()

    def st() -> str:
        proc = sh([*PIPE, "status", task_id, "--json"], cwd=repo,
                  check=False)
        return json.loads(proc.stdout)["status"]

    assert st() == "NEW"
    mock_produce(repo, task_id, "intent", 1)
    assert st() == "AWAITING_INTENT_CONSENT"
    sh([*PIPE, "consent", "intent", task_id], cwd=repo)
    assert st() == "RESEARCHING"
    mock_produce(repo, task_id, "findings", 2)
    mock_produce(repo, task_id, "planning", 3)
    assert st() == "AWAITING_PLAN_APPROVAL"
    sh([*PIPE, "consent", "plan", task_id, "--edited"], cwd=repo)
    assert st() == "IMPLEMENTING"
    mock_produce(repo, task_id, "execution", 4)
    mock_produce(repo, task_id, "review", 5)
    # D19: the merge gate stays shut until a passing check covers the
    # reviewed tree. Driven through the executable only, like everything
    # else in this acceptance path.
    assert st() == "UNVERIFIED"
    # Captured output lives outside the repo: A2's rollback asserts a
    # byte-identical tree, and verification evidence is not repo state.
    evidence = tmp_path / "verify-out.txt"
    evidence.write_bytes(b"3 passed\n")
    from reins import artifact      # harness only; the path under test is ENTRY
    diff_ref = artifact.consumed_hashes(
        artifact.load(HAPPY / "review.md"))["diff"]
    sh([*PIPE, "verify", task_id, "--verifier", "tests",
        "--tool", "pytest 9.1.1", "--predicate", "acceptance criteria pass",
        "--verdict", "pass", "--tree-ref", diff_ref,
        "--evidence-file", str(evidence)], cwd=repo)
    assert st() == "AWAITING_MERGE"
    sh([*PIPE, "validate", task_id], cwd=repo)
    sh([*PIPE, "decide", "merged", task_id, "--commit", "f00dfeed"],
       cwd=repo)
    assert st() == "DONE"
    sh([*PIPE, "extract", task_id, "--append"], cwd=repo)
    lines = [json.loads(l) for l in
             (repo / "telemetry.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    record = lines[0]
    assert record["outcome"] == "merged:f00dfeed"
    assert record["task_ref"] == "gh:123"
    assert record["plan_edited_at_gate"] is True
    # idempotency through the public interface too
    sh([*PIPE, "extract", task_id, "--append"], cwd=repo)
    assert len([l for l in (repo / "telemetry.jsonl").read_text()
                .splitlines() if l.strip()]) == 1

    # --- A2 rollback: documented deletion leaves a byte-identical tree
    import shutil
    shutil.rmtree(repo / ".dev")
    (repo / "telemetry.jsonl").unlink()
    for hook in (repo / ".claude" / "hooks").glob("*.sh"):
        hook.unlink()
    (repo / ".claude" / "hooks").rmdir()
    (repo / ".claude" / "settings.json").unlink()
    (repo / ".claude").rmdir()
    gi = (repo / ".gitignore")
    gi.write_text(gi.read_text().replace(".claude/settings.local.json\n", ""))
    assert tree_snapshot(repo) == before


# --- A4: dependency audit --------------------------------------------------

STDLIB_OK = {
    "argparse", "dataclasses", "datetime", "difflib",
    "hashlib", "json", "pathlib", "re", "sys", "typing", "warnings",
    "__future__",
}
THIRD_PARTY_OK: set[str] = set()   # D30: stdlib only


def test_A4_product_imports_are_stdlib_only():
    for py in (ROOT / "reins").glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                assert name in STDLIB_OK | THIRD_PARTY_OK | {"reins"}, (
                    f"{py.name} imports {name!r}")


def test_A4_dependency_direction_holds():
    """runtime -> pipeline is expected; pipeline -> runtime is forbidden

    (already enforced by test_product_never_references_runtime; this
    audit additionally confirms the runtime actually consumes the
    product's two public interfaces and nothing deeper)."""
    runtime = ROOT / "runtime"
    consumes_cli = consumes_contracts = False
    for f in runtime.rglob("*"):
        if not f.is_file():
            continue
        text = f.read_text(errors="ignore")
        if "reins_cli.py" in text or "reins.cli" in text or \
           "reins.validate" in text:
            consumes_cli = True
        if "reins/contracts" in text:
            consumes_contracts = True
        # nothing in the runtime may import product internals as a library
        assert "from reins import" not in text, f
        assert "import pipeline\n" not in text, f
    assert consumes_cli and consumes_contracts


def test_A4_decision_log_integrity():
    """M5's original claim was scoped: packaging (M0-M5) introduced no

    decision beyond D13. Later decisions are legitimate under
    docs/governance.md but must keep the D-format: numbered, with the
    four required fields."""
    import re
    text = (ROOT / "docs" / "implementation-decisions.md").read_text()
    assert "D13" in text  # last build-phase decision
    entries = re.findall(r"^## (D\d+)", text, re.M)
    numbers = [int(e[1:]) for e in entries]
    assert numbers == sorted(numbers) and len(numbers) == len(set(numbers))
    for block in re.split(r"^## D\d+", text, flags=re.M)[1:]:
        for field in ("**Problem:**", "**Why:**", "**Smallest change:**",
                      "**Why not architectural:**"):
            assert field in block, f"decision missing {field}"


def test_A1_entry_is_self_locating_without_pythonpath(tmp_path: Path):
    """F1 regression guard: the entry point must work with NO caller-side

    PYTHONPATH, no pip install, and a foreign cwd — the defect the suite
    previously masked by injecting PYTHONPATH into every subprocess."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, str(ENTRY), "init"], cwd=tmp_path,
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / ".dev" / "tasks").is_dir()


def test_A1_entry_guards_the_python_floor():
    """The version guard must exist, sit before any package import, and
    stay parseable by old interpreters so its message actually prints."""
    text = ENTRY.read_text()
    guard = text.index("sys.version_info < (3, 9)")
    assert guard < text.index("from reins.cli import main")
    assert "requires Python >= 3.9" in text
