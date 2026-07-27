#!/bin/sh
# PreToolUse hook: deterministic path protection (blueprint §9.1).
# Exit 2 blocks the tool call and feeds stderr back to Claude.
# Denies: secrets/keys always; .git internals; writes to immutable
# request.md and append-only telemetry.jsonl (D6).
INPUT=$(cat)
python3 - "$INPUT" << 'PYEOF'
import json, re, sys
data = json.loads(sys.argv[1])
tool = data.get("tool_name", "")
path = str(data.get("tool_input", {}).get("file_path", ""))
if not path:
    sys.exit(0)
deny_always = [r"(^|/)\.env($|\.)", r"\.(pem|key|p12|pfx)$", r"(^|/)\.git/"]
deny_write = [r"(^|/)\.dev/tasks/[^/]+/request\.md$", r"(^|/)telemetry\.jsonl$"]
for pat in deny_always:
    if re.search(pat, path):
        print(f"blocked: {path} matches protected pattern {pat}", file=sys.stderr)
        sys.exit(2)
if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
    for pat in deny_write:
        if re.search(pat, path):
            print(f"blocked: {path} is immutable/append-only (pipeline D6); "
                  "use the pipeline CLI instead", file=sys.stderr)
            sys.exit(2)
sys.exit(0)
PYEOF
exit $?
