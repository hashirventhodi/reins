#!/bin/sh
# PostToolUse hook: immediate feedback on artifact writes (blueprint §9.2).
# If the written path is a pipeline artifact, validate its task and feed
# violations to Claude via stderr + exit 2. For source files, delegates to
# the project's command if PIPELINE_POST_EDIT_CMD is set (per-stack; see
# settings.example.json), else exits 0.
# Invokes the core by path (D30): $REINS_HOME if set, else the
# installed ~/.claude/pipeline/core symlink; falls back to module
# invocation for development checkouts.
INPUT=$(cat)
python3 - "$INPUT" << 'PYEOF'
import json, os, re, subprocess, sys
data = json.loads(sys.argv[1])
path = str(data.get("tool_input", {}).get("file_path", ""))
m = re.search(r"(^|/)\.dev/tasks/([^/]+)/[^/]+\.md$", path)
if m:
    task_id = m.group(2)
    core = os.environ.get("REINS_HOME") or os.path.expanduser(
        "~/.claude/pipeline/core")
    entry = os.path.join(core, "pipeline_cli.py")
    cmd = ([sys.executable, entry, "validate", task_id]
           if os.path.exists(entry)
           else [sys.executable, "-m", "pipeline.cli", "validate", task_id])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 2:
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            sys.stderr.write(proc.stderr or proc.stdout)
            sys.exit(2)
        for a in report["artifacts"].values():
            for v in a["violations"]:
                print(f"pipeline: {v['artifact']}: {v['rule']}: "
                      f"{v['message']}", file=sys.stderr)
        for v in report["task_violations"]:
            print(f"pipeline: {v['rule']}: {v['message']}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
cmd = os.environ.get("PIPELINE_POST_EDIT_CMD")
if cmd and path:
    proc = subprocess.run(cmd.replace("{file}", path), shell=True,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        sys.exit(2)
sys.exit(0)
PYEOF
exit $?
