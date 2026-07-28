---
description: Audit or fit this repo's floor policy - propose presets, report limit fit, never write unapproved. Usage - /reins-policy [audit|propose]
---
Gather facts (the runtime owns git, D12), then let the product judge.

1. `git ls-files > /tmp/reins-paths.txt` — tracked paths only, so build
   output never looks like source.
2. Change sizes, one `<files> <lines>` per commit:
   `git log -n 50 --no-merges --format=%H | while read c; do git show
   --numstat --format= $c | awk '{f++; l+=$1+$2} END {print f+0, l+0}'; done
   > /tmp/reins-samples.txt`
3. `python3 ~/.claude/reins/core/reins_cli.py policy audit --paths-file
   /tmp/reins-paths.txt --samples-file /tmp/reins-samples.txt` — use
   `propose` for a repo with no policy, `presets` to list the bundles.

Present it as a decision: presets to add and why, presets to drop as
unnecessary, hand-written patterns that can never fire, and each ungoverned
area with an example file. For limits quote the express share and the
peer-review band together — raising a limit widens the cheap lane over
changes reviewers are measurably worse at, so it is a trade-off, never a fix.

Then STOP. Show the exact `.dev/config.yaml` diff and wait for an explicit
human reply. The floor is the agent's own oversight bar: propose it, never
record it (D18/D39). Write only what was approved.
