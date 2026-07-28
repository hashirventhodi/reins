# Changelog

## 2.0.0 — Reins (2026-07-28)

- `/reins-init` (D36) does the whole per-repo setup — task store, floor
  policy, hooks, settings, .gitignore — additively and idempotently,
  replacing six manual steps.
- Task arguments accept any unambiguous fragment of an id (D37):
  `/reins-work request-id` instead of the full
  `T-2026-07-28-add-a-request-id-header-…`. Ambiguity lists candidates
  rather than guessing; exact ids always win.
- One name everywhere (D35): commands are `/reins-work`, `/reins-task`,
  `/reins-status`, …; the package is `reins/`, the entry point
  `reins_cli.py`, the install path `~/.claude/reins/`. The `/pipeline-*`
  naming from D31 lasted one day and was refuted by first use: typing
  `/reins` found nothing. The artifact frontmatter key `pipeline:` is
  unchanged — that is the on-disk format, not a name in the UI.
- Licensed **MIT**.
- Public release; one-command install via skills.sh (D33, corrected by
  D34): `npx skills add hashirventhodi/reins -g` copies the entire
  system — root SKILL.md makes the repo itself the skill payload — and
  `/reins` wires in the commands, reviewer agent and core symlinks. No
  clone step, no vendoring, one copy of the core.
- The project is named **reins** (D32); repo
  `hashirventhodi/reins`, env override `$REINS_HOME`. Briefly named
  contract-runtime during the port.
- Runtime commands renamed to a claimed namespace: `/reins-work`,
  `/reins-task`, `/reins-status`, … (D31). The unprefixed names
  collided with other skill suites in `~/.claude/commands`; install.sh
  now also removes stale unprefixed links on upgrade.
- Repackaged so the core travels with its invoker (D30): it is invoked
  by path (`python3 ~/.claude/reins/core/reins_cli.py`), never
  installed. The `bin/` PATH shim is retired; `install.sh` adds the
  `~/.claude/reins/core` symlink.
- Zero dependencies: PyYAML replaced by the in-repo restricted-subset
  parser/dumper `reins/miniyaml.py`. Timestamps are now plain strings
  end-to-end (retires the D26 bug class at the parser).
- Python floor lowered to 3.9 and asserted at the entry point.
- New `scripts/selftest.py`: stdlib-only fresh-clone acceptance with
  frozen goldens.
- Reviewer diff base is an explicit input: the reviewer refuses to run
  without one and never falls back to `main` (runtime-only change).
- D28 (`frontmatter --init`, decorated-tag tolerance) and D29 (exit-3 is
  a status) landed with their tests and docs.
- Governance: policy evolved from "frozen: changes require telemetry" to
  "stable, not immutable" with a three-tier change ladder
  (docs/governance.md). The v1.0.0 entry below preserves the policy as
  written at tag time.
- Runtime: `/reins-followups` (then `/followups`) — review-driven task
  intake via the `followup:<parent>` source-ref convention (Tier 0; zero
  product changes).
- Adaptive workflow: the express lane, the computed floor and lane
  disposition (D18–D25); nothing merges unverified (D19).
- History note: the working tree was ported out of `contract-pipeline`
  v1.0.0 into a fresh repository (which is why the pre-port git history
  stays in `contract-pipeline`); that repository was then renamed
  contract-runtime -> reins, so its GitHub URLs redirect here (D32).
  Entries below are preserved as written — the commands they name were
  unprefixed at the time (D31).

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
