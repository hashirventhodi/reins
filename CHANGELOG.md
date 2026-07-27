# Changelog

## 2.0.0 — reins

- Public release; installable via skills.sh (D33): `npx skills add
  hashirventhodi/reins -g` ships the `/reins` bootstrap skill, which
  clones the repo and runs install.sh + selftest.
- The project is named **reins** (D32); repo
  `hashirventhodi/reins`, env override `$REINS_HOME`. Briefly named
  contract-runtime during the port.
- Runtime commands renamed to a claimed namespace: `/pipeline-work`,
  `/pipeline-task`, `/pipeline-status`, … (D31). The unprefixed names
  collided with other skill suites in `~/.claude/commands`; install.sh
  now also removes stale unprefixed links on upgrade.
- Repackaged as **contract-runtime** (D30): the deterministic core is
  invoked by path (`python3 ~/.claude/pipeline/core/pipeline_cli.py`),
  never installed. The `bin/` PATH shim is retired; `install.sh` adds the
  `~/.claude/pipeline/core` symlink.
- Zero dependencies: PyYAML replaced by the in-repo restricted-subset
  parser/dumper `pipeline/miniyaml.py`. Timestamps are now plain strings
  end-to-end (retires the D26 bug class at the parser).
- Python floor lowered to 3.9 and asserted at the entry point.
- New `scripts/selftest.py`: stdlib-only fresh-clone acceptance with
  frozen goldens.
- Reviewer diff base is an explicit input: the reviewer refuses to run
  without one and never falls back to `main` (runtime-only change).
- D28 (`frontmatter --init`, decorated-tag tolerance) and D29 (exit-3 is
  a status) landed with their tests and docs.
- History note: ported from `contract-pipeline` v1.0.0; its git history
  remains in that repository.

## Unreleased

- Governance: policy evolved from "frozen: changes require telemetry" to
  "stable, not immutable" with a three-tier change ladder
  (docs/governance.md). The v1.0.0 entry below preserves the policy as
  written at tag time.
- Runtime: /followups — review-driven task intake via the
  `followup:<parent>` source-ref convention (Tier 0; zero product
  changes).

## v1.0.0 — Contract Pipeline (2026-07-25) — FROZEN

The deterministic engineering-workflow product and its Claude Code
runtime binding. 185 tests; every architectural property executable.

- M0 — artifact model: parser/serializer/hashing, five canonical
  contract texts, generated happy-chain fixtures with real hashes
- M1 — type system: validator (24 rules, exhaustive matrix), transitive
  staleness, registry graph invariants at import time
- M2 — state machine: append-only decisions, pure deterministic
  frontier (15 statuses, normative precedence), thin CLI, mock-agent
  end-to-end proving model independence
- M3 — runtime binding: contract shims, /work orchestrator, read-only
  reviewer, three hooks; product/runtime boundary enforced by CI
- M4 — telemetry: pure projection generated from contract telemetry
  blocks; byte-reproducible records; idempotent on (task, outcome)
- M5 — packaging: install/migration/rollback/dependency audits as
  executable acceptance tests; zero new implementation decisions

Implementation decisions D1–D13 recorded (blueprint +
docs/implementation-decisions.md). None architectural.

Change policy from this tag forward: **no architectural changes without
telemetry** (docs/queries.md defines the quarterly review).
