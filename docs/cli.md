# CLI Reference — the deterministic API

The core is the API layer under the slash commands: the stable interface
runtime bindings, CI jobs, and hooks are built against. Day-to-day
development doesn't touch it — `/pipeline-task`, `/pipeline-work`, and `/pipeline-status` are the
user workflow — but it is a supported public surface with compatibility
guarantees, because model-independence depends on it.

The canonical invocation (D30) is by path, never via PATH:

    python3 ~/.claude/pipeline/core/pipeline_cli.py <command> ...

Throughout this document `pipeline <command>` abbreviates that line.
Hooks and non-Claude runtimes resolve the checkout through
`$REINS_HOME` (falling back to `~/.claude/pipeline/core`); a
development checkout can equivalently use `python3 -m pipeline.cli`
from the repo root.

Audiences:
- **Runtime authors** — implement the normative loop
  (docs/state-machine.md §orchestrator) by shelling out to these commands.
- **CI** — merge-time telemetry (`decide merged` + `extract --append`);
  see runtime/github/workflows/telemetry.yml.
- **Advanced / no-AI use** — every transition can be driven by hand; the
  M5 acceptance suite runs a full task through this surface alone.

## Exit codes

0 ok · 1 usage error · 2 validation failure / not extractable ·
3 needs-human (blocked or awaiting a consent gate)

3 is a **status, not a failure**: a healthy task waiting at a consent gate
exits 3 every time, by design, so a caller can branch on it. Chaining
`pipeline status` with `&&` or running it under `set -e` will therefore break
at exactly the moments a human is needed — branch on the code, or use `--json`
(D29).

`pipeline_cli.py` is self-locating (`realpath(__file__)`), so it runs
from any cwd with no pip install, no PYTHONPATH, and no venv, and it
asserts the Python ≥ 3.9 floor with a readable message before importing
anything. All commands are safe to re-run; `--json` gives
machine-readable output.

## Commands

Setup & intake
- `pipeline init` — create `.dev/`, config, empty telemetry log.
- `pipeline task add --title T [--body B | --body-file F] [--source-ref R]`
  — scaffold a task with an immutable, byte-exact `request.md`. This is
  the Task Source interface (D9): the *runtime* acquires the text (gh,
  MCP, user input) and passes it verbatim. Follow-up tasks use the source-ref convention
  `followup:<parent-task-id>` (docs/followups.md).
- `pipeline task list|show <id>`

Policy
- `pipeline floor <id> [--changed-paths-file F] [--lines-changed N] [--json]`
  — the minimum process a change deserves (D18). Facts are **supplied, not
  gathered**: git and repository inspection are the runtime's (D12), so the
  common invocation is
  `git diff --name-only | pipeline floor <id> --lines-changed N`.
  Policy lives in the `floor:` block of `.dev/config.yaml`
  (`governed_paths` globs, `max_files`, `max_lines`).
  **Fail-safe in one direction only:** no policy block, no supplied paths,
  or an unmeasured extent all yield `full`, never `express` — the floor
  exists to stop an agent lowering its own oversight, so every uncertainty
  resolves to more process. Every `full` verdict lists its reasons.
  Glob semantics are deliberately predictable: `*` stays within a path
  segment, `**` spans whole segments.
- `pipeline floor-check <id> [--changed-paths-file F] [--lines-changed N]
  [--json]` — the *realized* floor against the lane actually disposed
  (D20). `pipeline floor` is the prediction made before work from intended
  paths; this is the same function over what the diff turned out to be.
  Exit 2 on a lane violation, naming what raised the floor and how to
  resolve it. No disposition recorded means `full`, which no floor can
  exceed — so this is inert until a lane is chosen.

State
- `pipeline status <id> [--json]` — the derived Frontier (pure function
  of files; see docs/state-machine.md).
- `pipeline next <id>` — just the next contract name.
- `pipeline validate <id>` — the type system's report.

Decisions (append-only; the only stored state)
- `pipeline consent intent|plan <id> [--edited]` — hash-pinned consent.
  Intended to be invoked by the runtime's gate handling after an explicit
  human reply (the orchestrator auto-detects `--edited` by comparing the
  post-generation hash); invoke directly only in no-AI operation. Consent
  authenticity is procedural, not cryptographic (D7).
- `pipeline decide escalation|returned|merged <id> ...`
  (`bypass` was retired in D22 — the express lane replaced it and keeps
  adjudication. Existing records still read and still resolve to BYPASSED.)
- `pipeline decide disposition <id> --lane L --floor F [--reason R]` — the
  lane a task runs under, recorded against the floor it was chosen against
  (D20). `--reason` is required exactly when the lane is *below* the floor,
  and is rejected otherwise; it lands in telemetry as
  `disposition.overridden`, so override rate is a measurable quantity
  rather than a matter of trust.
- `pipeline verify <id> --verifier <slug> --tool <name+version>
  --predicate <claim> --verdict pass|fail|inconclusive
  --tree-ref git:<object id> (--evidence-file F | --evidence-hash H)
  [--standard-touched]` — record a verification result (D17).
  The **runtime** runs the check (tools, clocks, and git are its business);
  the product records the judgment and hashes the captured evidence, which
  it never parses. `--verifier` is an open slug so a new checker (lint,
  security, performance, migration) needs no product change.
  `--standard-touched` says the diff modified the standard this verifier
  judges by — its tests, rules, or allowlists.

Artifact plumbing (for skills and producers — never hand-compute hashes)
- `pipeline hash <file>`
- `pipeline frontmatter <file> --set k=v --pin artifact=path [--init]`
  `--init` creates the `---` fence when the file has none, leaving the body
  verbatim — the normal case when a contract skill has just written the
  artifact body. Without it a fenceless file is refused, as before (D28).
  A `--pin` target is either a **path** (the product hashes its exact bytes
  to `sha256:<64 hex>`) or an **already-formed reference** that passes
  through verbatim. Virtual artifacts use the latter: the review's diff pin
  is `git:$(git rev-parse HEAD^{tree})` — a git object reference, never a
  content hash and never re-hashed into one (D16).

Follow-ups
- `pipeline followups <id> [--json]` — deterministic candidate harvest
  (rules: docs/followups.md). Pure, read-only, projection only.
  Creation is the runtime's: it relays the human's selection to
  `pipeline task add` per candidate, extracting title/body from the
  JSON mechanically (never retyped), with
  `--source-ref "followup:<id>"`.

Telemetry
- `pipeline extract <id> [--append] [--telemetry PATH]` — pure projection,
  idempotent on (task, outcome); runs in CI at merge, or manually in
  local-first mode.
