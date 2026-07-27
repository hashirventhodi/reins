# Contract Pipeline — Agent Instructions

## What this is
The deterministic workflow engine governing AI-assisted development:
typed contracts, three approval gates, reproducible telemetry. You are
likely operating inside the workflow this repository implements.

## Operational Constitution
Every agent session inherits these; they outrank session-level judgment:
- The architecture is stable, not immutable (docs/governance.md).
- Evidence precedes redesign. Small, evidence-backed improvements over
  architectural reinvention.
- Deterministic derivation belongs in the product (pipeline/);
  orchestration belongs in the runtime (runtime/). The runtime never
  derives product state — it calls `pipeline` for facts.
- Human approval is explicit; never record consent without an explicit
  human reply in-session.
- Respect existing decision records before introducing new principles:
  docs/implementation-decisions.md is case law (D9 ownership, D12/D14
  actor-determines-layer, D15 diff currency, D16 reference identities,
  D18 the floor is computed not judged, D21 lanes parameterise, never fork).
- An agent may *propose* how much process a task deserves. It may never
  record that choice: the floor is computed, the lane is the human's, and
  an override is loud, reasoned, and counted (D18/D20/D22).
- Friction is product feedback, not user error. Telemetry measures what
  the system sees; the friction log captures what it cannot.

## Commands that aren't obvious
- `python3 -m pytest -q` — 339 tests; must stay green.
- `python3 scripts/selftest.py` — stdlib-only fresh-clone acceptance (D30);
  must pass under the oldest supported interpreter (3.9).
- `python3 scripts/regen_fixtures.py` — after intentional fixture changes.
  Writes both executable specifications: `tests/fixtures/happy/` (full lane)
  and `tests/fixtures/express/`. Never hand-edit hashes; the diff pin is
  derived from a real throwaway git repo.

## Pitfalls — what agents get wrong here
- The core is invoked by path: `python3 ~/.claude/pipeline/core/pipeline_cli.py
  <cmd>` (docs use `pipeline <cmd>` as shorthand). There is no installed
  `pipeline` binary and nothing on PATH (D30); a dev checkout may use
  `python3 -m pipeline.cli`.
- Never reintroduce PyYAML (or any dependency). Frontmatter/ledger/config
  YAML is the `pipeline/miniyaml.py` restricted subset (D30); anything
  outside it must fail loudly, not get a new parser feature by default.
- Never hand-compute or retype artifact hashes or candidate bodies; use
  `pipeline hash` / `pipeline frontmatter --pin` / mechanical extraction.
- Two reference identities, not interchangeable (D16): `sha256:<64 hex>` for
  content artifacts, `git:<object id>` for virtual ones. Never re-hash a git
  object id to make it look like a content hash.
- Facts fed to `pipeline floor` / `floor-check` are the **source** change:
  exclude `.dev/**` and `telemetry.jsonl`, or task bookkeeping pushes every
  task to `full`.
- `consumes_alt` is a compatibility mechanism, not a second pipeline. The
  validator accepts either complete pin set and rejects mixtures; only the
  frontier knows which is legal for the lane in force.
- Contract texts (contracts/) and schemas.py are parity-tested; change
  both or neither, via the governance ladder.
- A nonzero exit is often a status, not a failure: `status`/`next` exit 3
  at a consent gate by contract (docs/cli.md, D29). Branch on the code or
  parse `--json`; never chain them with `&&` or run them under `set -e`.
- Write the artifact body first, then `pipeline frontmatter … --init` to
  create the fence and pin (D28). Never hand-write a fence or a hash.
- The test-count badge and docs counts are static; sync them when the
  suite grows.

## Do not touch
- `request.md` files and `telemetry.jsonl` are immutable/append-only
  (hook-enforced, D6).
- Decision logs are append-only; never rewrite history.

## Deeper docs (read when relevant)
- Phase charter: docs/handoff.md · Governance: docs/governance.md
- State machine: docs/state-machine.md · Operations: docs/operations.md
