# Contributing

Thanks for your interest. Two ground rules shape everything here:

1. **Stable, not immutable — changes climb the ladder.** See
   docs/governance.md. Contracts, gates, statuses, and artifact schemas
   (Tier 2) need a written case with a pre-registered kill criterion and
   at least one grounding instance: a telemetry signal, a reproducible
   failure, or one concrete task where the current design got in the
   way. Elegance alone doesn't clear Tier 2.
2. **The runtime orchestrates, never decides.** If your change adds logic
   to `runtime/`, ask whether it belongs in `pipeline/` instead — CI will
   ask regardless.

## High-value contributions

- **Runtime bindings** for other agents (Cursor, OpenCode, Codex CLI…).
  Implement the normative loop in docs/state-machine.md against the two
  public interfaces (the core's subcommands + contract texts). Add a
  `runtime/<name>/` dir; never import product internals as a library.
  Point `$REINS_HOME` at a checkout and invoke
  `python3 "$REINS_HOME/pipeline_cli.py" <cmd>` — no install step exists
  to depend on (D30).
- **Telemetry from real usage** — anonymized `telemetry.jsonl` excerpts
  with observations, especially where a contract looks vestigial or
  hollow.
- **Validator rules** — must ship with a passing and a failing fixture
  (the meta-test `test_every_rule_id_is_covered` enforces this) and stay
  mechanical (presence/tags/enums, never prose quality: the validator
  checks structure, never whether the writing is any good).

## Working on the code

```console
python3 -m pip install -e '.[dev]'   # pytest only; the product has no deps
python3 -m pytest -q          # 340 tests, ~10s; must stay green
python3 scripts/selftest.py   # stdlib-only deployment acceptance (D30)
python3 scripts/regen_fixtures.py   # after intentional fixture changes
python3 scripts/selftest.py --regen # ONLY after intentional fixture changes:
                                    # refreezes scripts/goldens/; commit both
```

Implementation decisions that operationalize underspecified behavior go in
docs/implementation-decisions.md in the D-format (problem / why / smallest
change / why not architectural). PRs that need a D-entry and don't have
one will be asked for it.

## Style

Python ≥ 3.9, stdlib only in `pipeline/` (audited by test; YAML is
handled by the in-repo `pipeline/miniyaml.py` subset — D30). No new
dependencies, period.
