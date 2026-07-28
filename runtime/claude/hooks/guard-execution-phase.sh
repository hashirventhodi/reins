#!/bin/sh
# PreToolUse hook (ships DISABLED; enable per repo — blueprint §9.3).
# Deterministic backing for E2 and P3: while any task is IMPLEMENTING,
# block edits to dependency manifests and to plan.md. Fails open if the
# pipeline is unavailable.
INPUT=$(cat)
python3 - "$INPUT" << 'PYEOF'
import json, os, re, subprocess, sys
data = json.loads(sys.argv[1])
if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
    sys.exit(0)
path = str(data.get("tool_input", {}).get("file_path", ""))
if not path:
    sys.exit(0)
try:
    core = os.environ.get("REINS_HOME") or os.path.expanduser(
        "~/.claude/reins/core")
    entry = os.path.join(core, "reins_cli.py")
    cmd = ([sys.executable, entry, "task", "list", "--json"]
           if os.path.exists(entry)
           else [sys.executable, "-m", "reins.cli", "task", "list", "--json"])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    rows = json.loads(proc.stdout or "[]")
except Exception:
    sys.exit(0)  # fail open: guard is best-effort backing, not the gate
implementing = [r["task"] for r in rows if r.get("status") == "IMPLEMENTING"]
if not implementing:
    sys.exit(0)
manifests = (r"(^|/)package\.json$", r"(^|/)pyproject\.toml$",
             r"(^|/)go\.mod$", r"(^|/)Cargo\.toml$", r"(^|/)Gemfile$",
             r"(^|/)requirements[^/]*\.txt$")
if any(re.search(p, path) for p in manifests):
    print(f"blocked (E2): dependency manifest edits during IMPLEMENTING "
          f"({implementing[0]}) require escalation: pipeline decide "
          f"escalation {implementing[0]} --trigger E2 --from execution "
          "--detail '...'", file=sys.stderr)
    sys.exit(2)
if re.search(r"(^|/)\.dev/tasks/[^/]+/plan\.md$", path):
    print("blocked (P3): the implementer may not edit the plan; propose a "
          "return to planning instead", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
PYEOF
exit $?
