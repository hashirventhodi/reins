<div align="center">

# Reins

**A deterministic workflow engine for AI coding agents.**
**Your AI writes the code. Reins governs the process — typed contracts, human approval gates, reproducible telemetry.**

[![tests](https://img.shields.io/badge/tests-340%20passing-brightgreen)](tests/)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](pyproject.toml)
[![deps](https://img.shields.io/badge/dependencies-none%20(stdlib%20only)-lightgrey)](pyproject.toml)
[![status](https://img.shields.io/badge/v2.0.0-stable-8A2BE2)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

Consequential work moves through five contracted phases and pauses at three
points for your approval. Everyday work takes the **express lane** — one
stop, still reviewed and still verified — and which lane applies is computed
from the change, not argued by the agent. Either way it leaves a reproducible
evidence trail. Reins ships with a Claude Code runtime, so all of
it is conversational: `/reins-task add`, `/reins-work`, done.

AI coding agents are great at writing code and terrible at accountability.
They plan in their heads, drift from what you asked, review their own work,
and leave no record of any of it.

Reins replaces vibes with **five typed contracts**. Each phase of
a task consumes one artifact and produces the next — hash-pinned, validated,
and reviewable — with up to **three human approval gates**: confirm the
intent, approve the plan, merge the result. Everything in between is
autonomous *within contract*, and everything that happens becomes one line of
telemetry that decides how the process itself evolves.

How much process a task gets is the one thing an agent may propose but never
decide. A **computed floor** — governed paths, diff extent, repo policy —
sets the minimum; you choose the lane at or above it; going below is possible,
but it is written down, reasoned, and counted. Nothing merges unreviewed and
nothing merges unverified, on any lane.

```mermaid
flowchart LR
    A[Request] --> B[Intent]
    B -- "🚪 gate 1<br/>you confirm" --> C[Plan]
    C -- "🚪 gate 2<br/>you approve" --> D[Implementation]
    D --> E[Review<br/><i>fresh context</i>]
    E -- "🚪 gate 3<br/>you merge" --> F[(Telemetry)]
```

Every finished task becomes one reproducible line of evidence:

```json
{"outcome": "merged:f00dfeed", "plan_edited_at_gate": true,
 "escalations": [{"trigger_id": "E2"}], "undeclared_deviations_found": false}
```

That's the governance loop: the contracts are hypotheses about how
development should work, and telemetry is how they're tested. Contracts
that stop earning their keep get deleted.

The agent never decides its own status, never computes a hash, and never
reviews its own work — review runs in **fresh context** with read-only tools,
adjudicating the diff against the approved plan and the agent's own
**deviation ledger**. An empty ledger isn't an omission; it's a signed claim
the reviewer tests.

## Highlights

- 🧾 **Artifacts are the API.** Five markdown artifacts with schemas,
  required sections, and `sha256`-pinned upstream hashes. Edit anything
  upstream and everything downstream goes stale — transitively, automatically.
- 🚦 **Three approval gates, zero babysitting.** Approval is pinned to the
  exact bytes you approved; editing an approved plan reopens the gate.
  Between gates, `/reins-work` runs the whole loop.
- 🛑 **Escalation is compliance, not failure.** Five triggers (invalidated
  assumption, unplanned dependency, repeated verification failure, scope
  blow-up, checkpoint) *halt* execution and route backward — by contract.
- 🔍 **Deterministic core, auditable everywhere.** Status is a pure function
  of files — no daemon, no database, byte-identical output for identical
  inputs. A shell script can drive the entire state machine (we test that).
- 📊 **Telemetry that governs.** Every merged task appends one reproducible
  JSON record answering the questions each contract pre-registered to
  justify its own existence — including which lane it ran and whether the
  floor was overridden — and [ten jq queries](docs/queries.md) run the trial.
- 🔌 **Agent-agnostic by construction.** The core is contracts + a
  deterministic Python package invoked by path — no install, no PATH, no
  dependencies, so it behaves identically in Claude Code, Codex, CI, or a
  bare shell. Claude Code binding included; any runtime that can shell out
  can drive it. CI enforces that the product never references any runtime.
- 📦 **Installs as one skill, carries everything.** `npx skills add
  hashirventhodi/reins` delivers the core, the contract texts, the runtime
  and the executable fixtures in a single copy — then `/reins` wires it in
  and proves determinism on your machine with a stdlib-only selftest.

## Quick start

Requires Python ≥ 3.9 and git. **Zero dependencies** — nothing is
pip-installed and nothing lands on PATH.

Install via [skills.sh](https://skills.sh) — the repository *is* the
skill, so this one command carries the whole system, not a stub (D34):

```console
$ npx skills add hashirventhodi/reins -g
```

Then invoke `/reins` in your agent once. It wires the `/reins-*`
commands, the contract skills and the reviewer agent into `~/.claude`,
and runs a stdlib-only selftest that proves the core derives
deterministically on your machine.

<details>
<summary>Prefer a git checkout? Same result, three commands.</summary>

```console
$ git clone https://github.com/hashirventhodi/reins ~/Code/tools/reins
$ cd ~/Code/tools/reins && ./install.sh
$ python3 scripts/selftest.py
```
</details>

In any repository, set it up once — one command, additive and
idempotent:

```text
/reins-init
```

The bundled **Claude Code runtime** is what provides the slash commands —
`/reins-task`, `/reins-work`, `/reins-status` — as thin bindings over the deterministic
core. (Other agents can provide the same commands by implementing the
[normative loop](docs/state-machine.md); Claude Code is simply the first
runtime.) Then everything is conversational:

```text
/reins-task add Add a request id header to every API response
/reins-work T-2026-07-25-add-a-request-id-header
```

(`/reins-task add` prints the task ID — use the one it gives you.)

`/reins-work` runs contract to contract and stops only when it needs you: it
shows you the intent to confirm, the plan to approve, and reports when the
task is ready to merge. Check in anytime with `/reins-status <task-id>`.

Full setup: **[docs/install.md](docs/install.md)** ·
Existing repos (10 min, fully reversible): **[docs/migration.md](docs/migration.md)**

## What a task looks like

<!-- demo.gif: recorded with `vhs demo.tape` (see assets/demo.tape) once
     you have a real /reins-work run — do not fake this recording. Suggested
     shots: /reins-task add -> /reins-work -> gate 2 approval -> review verdict ->
     telemetry line. -->

`/reins-work` pauses at gate 2 and shows you the plan:

> **Plan ready for approval** (gate 2 of 3) — objective, three steps each with
> a `verify:` line, risks, out of scope. *Approve, edit, or send it back?*

You read it for two minutes — the highest-leverage two minutes in the
workflow — tighten the out-of-scope section, and say **"approved."** The
orchestrator notices your edit and records it (`plan_edited_at_gate:
true`): gates that get edited are gates that are working.

Mid-implementation, the agent discovers it needs a dependency the plan
never named. It doesn't improvise — trigger **E2** fires, execution halts,
and `/reins-work` stops to ask you where to route it. After you merge the PR, CI
appends one reproducible record to `telemetry.jsonl`:

```json
{
  "outcome": "merged:f00dfeed",
  "escalations": [{"trigger_id": "E2", "from_contract": "execution"}],
  "ledger_entries": {"count": 1, "by_status": {"within-autonomy": 1}},
  "plan_edited_at_gate": true,
  "undeclared_deviations_found": false
}
```

Under the slash commands sits the deterministic core — the API the
runtime drives, and the reason none of this depends on any particular
agent. It is a stdlib-only Python package invoked by path
(`python3 ~/.claude/reins/core/reins_cli.py …`), never installed,
so there is no version of it to get wrong. A human can run every
transition by hand (that's not a fallback; it's the model-independence
proof, enforced by an end-to-end test where a shell script plays the
agent). Runtime authors and advanced users: see the
**[command reference](docs/cli.md)**.

## Design principles

1. **Contracts are the constitution.** Phases are implementations; the five
   contract texts in [`contracts/`](contracts/) are the spec, and code is
   parity-tested against them.
2. **The runtime orchestrates, never decides.** All logic lives in the
   deterministic core; the agent binding is thin prompts over it — and a
   CI test fails if the product ever references a runtime.
3. **Store decisions, derive status.** The only stored state is an
   append-only log of human decisions. Everything else is computed, which is
   why crashing and resuming is a non-event.
4. **Enforcement over instruction.** Hard rules (immutable requests,
   append-only telemetry, no manifest edits mid-implementation) are hooks
   and validators, not prompt suggestions.
5. **Stable, not immutable.** The architecture evolves deliberately —
   on written cases grounded in real usage, reproducible failures, or
   telemetry — never by taste alone. See [governance](docs/governance.md).

## Documentation

| Guide | What it covers |
|---|---|
| [Installation](docs/install.md) | Fresh-machine setup — one command via skills.sh, or a git checkout |
| [Migration](docs/migration.md) | Adopt in an existing repo; byte-identical rollback |
| [State machine](docs/state-machine.md) | The 16 statuses, lanes, normative precedence, clearing rules |
| [Architecture](docs/architecture.md) | Modules, invariants, the product/runtime boundary |
| [Command reference](docs/cli.md) | The deterministic API under the slash commands — for runtime authors, CI, and no-AI use |
| [The contracts](contracts/) | Canonical texts — Intent, Findings, Planning, Execution, Review |
| [Quarterly review](docs/queries.md) | The ten queries that put the process itself on trial |
| [Implementation decisions](docs/implementation-decisions.md) | D10–D34, the honest record — including the ones that were later corrected |

## Contributing

The core is deliberately small and changes only through the
[governance ladder](docs/governance.md); the most valuable contributions
right now are **runtime bindings** (Cursor, OpenCode, Codex CLI — the
[orchestration loop is normative](docs/state-machine.md), and
`$REINS_HOME` points any runtime at a checkout) and **telemetry from real
usage**. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Hashir V
