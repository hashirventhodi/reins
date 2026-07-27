"""M3 acceptance: the runtime binding is a pure consumer of the product.

Tests here cover: hook behavior against recorded PreToolUse/PostToolUse
JSON (exit-code contracts), install.sh idempotence into a temp HOME, shim
and command integrity (every skill references an existing canonical
contract; commands stay thin), the reviewer agent's read-only posture,
and the one-way dependency boundary (nothing in pipeline/ references
runtime/)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime" / "claude"
HOOKS = RUNTIME / "hooks"
HAPPY = next((ROOT / "tests" / "fixtures" / "happy").iterdir())


def run_hook(script: str, payload: dict, cwd: Path | None = None,
             env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env["PYTHONPATH"] = str(ROOT)
    full_env.update(env or {})
    return subprocess.run(
        ["sh", str(HOOKS / script)], input=json.dumps(payload),
        capture_output=True, text=True, cwd=cwd or ROOT, env=full_env)


def pre(tool: str, path: str) -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": path}}


# --- protect-paths.sh ------------------------------------------------------

@pytest.mark.parametrize("tool,path,code", [
    ("Read", ".env", 2),
    ("Edit", "config/.env.production", 2),
    ("Write", "certs/server.pem", 2),
    ("Edit", ".git/config", 2),
    ("Edit", ".dev/tasks/T-x/request.md", 2),          # D6 immutability
    ("Write", "telemetry.jsonl", 2),                   # D6 append-only
    ("Read", ".dev/tasks/T-x/request.md", 0),          # reading is fine
    ("Edit", "src/api/app.py", 0),
    ("Edit", ".dev/tasks/T-x/intent.md", 0),
    ("Write", "docs/environment.md", 0),
])
def test_protect_paths(tool, path, code):
    proc = run_hook("protect-paths.sh", pre(tool, path))
    assert proc.returncode == code, proc.stderr
    if code == 2:
        assert "blocked" in proc.stderr


def test_protect_paths_no_path_is_noop():
    proc = run_hook("protect-paths.sh",
                    {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    assert proc.returncode == 0


# --- post-edit-check.sh ----------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    d = tmp_path / ".dev" / "tasks" / HAPPY.name
    shutil.copytree(HAPPY, d)
    return tmp_path


def test_post_edit_valid_artifact_passes(repo: Path):
    rel = f".dev/tasks/{HAPPY.name}/intent.md"
    proc = run_hook("post-edit-check.sh", pre("Edit", rel), cwd=repo)
    assert proc.returncode == 0, proc.stderr


def test_post_edit_invalid_artifact_feeds_violations(repo: Path):
    target = repo / ".dev" / "tasks" / HAPPY.name / "intent.md"
    target.write_text(target.read_text().replace("## Non-goals", "## Nope"))
    rel = f".dev/tasks/{HAPPY.name}/intent.md"
    proc = run_hook("post-edit-check.sh", pre("Edit", rel), cwd=repo)
    assert proc.returncode == 2
    assert "section-missing" in proc.stderr   # quotable rule id for the skill


def test_post_edit_source_file_delegates_to_project_cmd(repo: Path):
    proc = run_hook("post-edit-check.sh", pre("Edit", "src/x.py"), cwd=repo,
                    env={"PIPELINE_POST_EDIT_CMD": "false"})
    assert proc.returncode == 2
    proc = run_hook("post-edit-check.sh", pre("Edit", "src/x.py"), cwd=repo,
                    env={"PIPELINE_POST_EDIT_CMD": "true"})
    assert proc.returncode == 0
    proc = run_hook("post-edit-check.sh", pre("Edit", "src/x.py"), cwd=repo)
    assert proc.returncode == 0                # no project cmd -> no-op


# --- guard-execution-phase.sh ----------------------------------------------

def make_implementing(repo: Path) -> None:
    d = repo / ".dev" / "tasks" / HAPPY.name
    (d / "ledger.md").unlink()
    (d / "review.md").unlink()


def test_guard_blocks_manifest_and_plan_edits_while_implementing(repo: Path):
    make_implementing(repo)
    proc = run_hook("guard-execution-phase.sh", pre("Edit", "package.json"),
                    cwd=repo)
    assert proc.returncode == 2 and "E2" in proc.stderr
    rel = f".dev/tasks/{HAPPY.name}/plan.md"
    proc = run_hook("guard-execution-phase.sh", pre("Edit", rel), cwd=repo)
    assert proc.returncode == 2 and "P3" in proc.stderr
    proc = run_hook("guard-execution-phase.sh", pre("Edit", "src/x.py"),
                    cwd=repo)
    assert proc.returncode == 0


def test_guard_is_inert_when_not_implementing(repo: Path):
    proc = run_hook("guard-execution-phase.sh", pre("Edit", "package.json"),
                    cwd=repo)  # fixture task is AWAITING_MERGE
    assert proc.returncode == 0


def test_guard_fails_open_outside_a_pipeline_repo(tmp_path: Path):
    proc = run_hook("guard-execution-phase.sh", pre("Edit", "package.json"),
                    cwd=tmp_path)
    assert proc.returncode == 0


# --- install.sh ------------------------------------------------------------

def test_install_is_idempotent_and_links_everything(tmp_path: Path):
    env = dict(os.environ, CLAUDE_HOME=str(tmp_path / "claude-home"))
    for _ in range(2):  # idempotence
        proc = subprocess.run(["sh", str(ROOT / "install.sh")],
                              capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stderr
    home = tmp_path / "claude-home"
    for skill in RUNTIME.joinpath("skills").iterdir():
        assert (home / "skills" / skill.name / "SKILL.md").exists()
    for cmd in RUNTIME.joinpath("commands").glob("*.md"):
        assert (home / "commands" / cmd.name).exists()
    assert (home / "agents" / "reviewer.md").exists()
    assert (home / "pipeline" / "contracts" / "planning.md").exists()
    assert (home / "pipeline" / "core" / "pipeline_cli.py").exists()


# --- binding integrity -----------------------------------------------------

def test_every_contract_has_a_skill_shim_and_vice_versa():
    from pipeline.schemas import CONTRACTS
    shims = {p.name.removesuffix("-contract")
             for p in RUNTIME.joinpath("skills").iterdir()}
    assert shims == set(CONTRACTS)


def test_shims_reference_canonical_contracts_and_forbid_hand_hashes():
    for shim in RUNTIME.joinpath("skills").glob("*/SKILL.md"):
        text = shim.read_text()
        contract = shim.parent.name.removesuffix("-contract")
        assert f"pipeline/contracts/{contract}.md" in text
        assert (ROOT / "contracts" / f"{contract}.md").exists()
        assert "Never hand-write" in text
        assert "pipeline_cli.py frontmatter" in text
        assert len(text.splitlines()) <= 16   # shims stay thin


def test_commands_stay_thin():
    """The guard is against the runtime reimplementing product logic, so it

    stays tight for every command that wraps one contract. `work.md` is the
    exception by nature: it is the normative loop, a dispatch table with one
    branch per status, and the state machine has 16 of them. Its own cap is
    higher but still bounded — the real guard against it growing logic is
    test_work_command_encodes_the_normative_loop below, which asserts it
    delegates rather than derives."""
    for cmd in RUNTIME.joinpath("commands").glob("*.md"):
        body = cmd.read_text().split("---", 2)[2]
        limit = 30 if cmd.name == "work.md" else 22
        assert len(body.strip().splitlines()) <= limit, cmd.name


def test_work_command_encodes_the_normative_loop():
    text = (RUNTIME / "commands" / "work.md").read_text()
    for required in ("pipeline_cli.py status", "pipeline_cli.py validate",
                     "2 correction",
                     "reviewer subagent", "consent", "--edited",
                     "Never compute status yourself",
                     "/dispose",          # the human chooses the lane
                     "UNVERIFIED",        # D19, resolved mechanically
                     "/verify",
                     "floor-check"):      # D20, realized floor at the gate
        assert required in text, required


def test_runtime_gathers_source_facts_not_repository_facts():
    """The product consumes facts; the runtime decides how they are gathered

    (D18/D12). Task bookkeeping is committed on the branch, so an unfiltered
    `git diff --name-only` counts .dev/ and telemetry.jsonl and pushes every
    task to `full`. Forgetting to filter fails safe — more process, never
    less — but the instruction has to exist somewhere, and here is where."""
    dispose = (RUNTIME / "commands" / "dispose.md").read_text()
    assert ".dev/**" in dispose and "telemetry.jsonl" in dispose
    assert "SOURCE change only" in dispose
    assert "pipeline_cli.py floor" in dispose
    # the gate re-checks against the same filtered set
    assert "filtered as in /dispose" in (
        RUNTIME / "commands" / "work.md").read_text()


def test_gates_are_presented_one_at_a_time():
    """Confirming intent after a plan exists anchors the human to the plan,

    which is what gate 1 exists to prevent. The express lane, not batching,
    is how the stop count comes down."""
    text = (RUNTIME / "commands" / "work.md").read_text()
    assert "one at a time" in text and "anchors" in text


def test_shims_know_the_express_pin_sets():
    """A lane changes which artifacts exist, so the two contracts whose

    consumes_alt differs must say so, or they will pin the full-lane set on
    a task that has no intent.md."""
    execution = (RUNTIME / "skills" / "execution-contract" / "SKILL.md").read_text()
    review = (RUNTIME / "skills" / "review-contract" / "SKILL.md").read_text()
    assert "express lane" in execution and "pin request instead of plan" in execution
    assert "express lane" in review and "pin request, ledger and" in review


def test_the_agent_never_decides_its_own_oversight():
    """The invariant Phase 0 established and D22 completed: an agent may

    propose how much process a task deserves, never record it. The intent
    shim proposes and stops (asserted here because /refine reaches it
    directly), and /work forbids recording any of it without an explicit
    human reply."""
    shim = (RUNTIME / "skills" / "intent-contract" / "SKILL.md").read_text()
    assert "PROPOSAL" in shim and "never self-recorded" in shim
    assert "pipeline_cli.py decide disposition" in shim
    assert "decide bypass" not in shim      # retired (D22)
    work = (RUNTIME / "commands" / "work.md").read_text()
    assert ("never record a consent or a bypass without an explicit human "
            "reply in-session") in work


def test_reviewer_agent_is_read_only_and_isolated():
    text = (RUNTIME / "agents" / "reviewer.md").read_text()
    for tool in ("Edit", "Write", "MultiEdit"):
        assert f" {tool}," not in text.split("---")[1]  # not in tools list
    assert "read-only" in text.lower()
    assert "never with session content" in text.lower() or \
           "never edit source files" in text.lower()


def test_product_never_references_runtime():
    """D9: one-way dependency, enforced by scanning for actual references

    (paths/imports), not prose mentions of the word 'runtime'."""
    forbidden = ("runtime/claude", "runtime.claude", "from runtime",
                 "import runtime")
    for py in (ROOT / "pipeline").glob("*.py"):
        text = py.read_text()
        assert not any(f in text for f in forbidden), py.name
    for contract in (ROOT / "contracts").glob("*.md"):
        text = contract.read_text()
        assert not any(f in text for f in forbidden), contract.name
        assert "SKILL.md" not in text, contract.name


def test_followups_command_respects_the_boundaries():
    """Follow-ups are runtime intake (D9/D14): the CLI harvests
    deterministically; the runtime presents and relays explicit human
    selection, deriving nothing itself and touching no external
    trackers."""
    text = (RUNTIME / "commands" / "followups.md").read_text()
    for required in ("pipeline_cli.py followups $ARGUMENTS --json",
                     "never derive candidates", "pipeline_cli.py task add",
                     "MECHANICALLY", "never retyped",
                     'followup:$ARGUMENTS', "explicit human",
                     "already_created", "Never create GitHub/Jira"):
        assert required in text, required
