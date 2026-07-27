# Implementation Decisions (repo-local log)

D1–D9 live in the implementation blueprint. Decisions made during the
build continue the same numbering and format here.

## D10 — 15 explicit statuses instead of the blueprint's 13

- **Problem:** the blueprint's status list said "13" but its own
  algorithm implied more: step 1 requires a state for "violations exist,
  nothing may run" (INVALID), and NEW vs REFINING were listed as
  distinct but looked underivable from files alone.
- **Why:** INVALID was implicit in "no contract may run until fixed";
  making it explicit beats overloading STALE or BLOCKED. NEW/REFINING
  turned out to be derivable after all: NEW iff only request.md exists
  AND the decision log is empty; any decision record means work started.
- **Smallest change:** enumerate all 15 in `frontier.STATUSES`, add a
  fixture per status, and a meta-test that the fixture set equals the
  status set (the matrix cannot silently shrink).
- **Why not architectural:** no transition, gate, or contract changed;
  the state space was made explicit and total, which the frozen
  algorithm already required. Documented normatively in
  docs/state-machine.md.

## D11 — deterministic clearing rules for escalations and returns

- **Problem:** the blueprint said "latest returned decision newer than
  its target artifact overrides" and "latest unresolved escalation ->
  BLOCKED" without defining "newer" or "unresolved" operationally.
- **Why:** any definition consulting wall clocks or mtimes would break
  frontier determinism.
- **Smallest change:** escalation resolved by any later `returned`
  decision in log order; decision-based return pending until the target
  artifact's `produced_at` (frontmatter, ISO-8601 UTC) is lexically
  greater than the decision `ts`; verdict-based returns clear via
  STALE precedence when the target regenerates.
- **Why not architectural:** the transitions and their meanings are
  unchanged; previously implicit behavior became deterministic content
  of the same rules.

## D12 — no git operations in the pipeline; `pipeline merge` does not exist

- **Problem:** the blueprint's §10 fallback described a `pipeline merge`
  wrapper performing the squash-merge, but the accepted D9 ownership
  split places git operations in the runtime.
- **Why:** D9 supersedes: the product must not acquire a git client for
  the same reason it must not acquire a forge client — the boundary is
  structural, not promised.
- **Smallest change:** the primitive is `pipeline extract <task>
  --append` (idempotent). The flow — runtime/CI merges, records
  `decide merged --commit <sha>`, then extracts — lives in the CI
  template (runtime/github/workflows/telemetry.yml) and docs.
- **Why not architectural:** telemetry timing, content, and idempotency
  are unchanged; only the actor performing git moved to where D9 already
  assigned it.

## D13 — self_corrections emits null in v1

- **Problem:** the D8 self-correction count is orchestrator-side
  knowledge with no recording mechanism: the decision enum is closed
  and adding a type is a versioned schema change.
- **Why:** a metric that cannot be computed emits null, never a guess
  and never a block (blueprint invariant).
- **Smallest change:** the metric function returns None; the field stays
  in every record so the schema is stable when v2 adds a recording path
  (candidate: a `note` decision type or an orchestrator-written count in
  review frontmatter).
- **Why not architectural:** the metric remains declared by the
  Execution Contract; only its computability in v1 is documented.

## D14 — deterministic follow-up harvesting lives in the product (Tier 1)

- **Problem:** the first /followups implementation had the runtime prompt
  derive candidates from four artifacts. A prompt cannot guarantee
  order, dedup, or run-to-run identity — and derivation over artifacts
  is the same category of work as computing status, which the runtime is
  forbidden to do.
- **Why:** determinism is a product property, enforced by code; the
  harvest is a pure read-only projection, exactly like frontier and
  telemetry.
- **Smallest change:** `pipeline followups <id> [--json] [--create i,j]`
  — normative extraction rules (chain order; /defer/i non-goals; all
  out-of-scope observations; ledger entries with plan_impact != none;
  should-fix/nit review findings), exact-normalized dedup with origin
  accumulation, word-boundary titles (<=72), verbatim bodies + fixed
  origin line, already-created detection via the followup: source-ref,
  and deterministic creation relaying explicit human selection. The
  runtime command shrinks to present-and-relay.
- **Why not architectural:** additive, backward-compatible, read-only
  except --create (which composes the existing task-add path); no
  schema, gate, status, or enum change; PIPELINE_VERSION unchanged.
  First exercise of the governance ladder's Tier 1.

### D14, amended — creation moved to the runtime

- **Problem:** `--create` bundled orchestration (iterate over a human
  selection, perform creations) into the product.
- **Why:** the D12 precedent — deterministic mechanics don't fix a wrong
  actor. Projection is product; performing selected work is runtime.
- **Smallest change:** `pipeline followups` is projection-only; the
  runtime invokes the existing `task add` primitive per selection,
  extracting bytes from the harvest JSON mechanically. `creation_body()`
  remains the normative byte spec; already-created skip is
  runtime-primary with the task-add slug collision as backstop.
- **Why not architectural:** removes a command; no schema or interface
  the runtime relied on beyond what remains.

## D15 — diff currency is a runtime obligation at gate 3

- **Problem:** D5 pins the branch tree hash in review.md and promised
  "staleness = new commits after review," but the validator skips
  virtual artifacts — post-review commits left the review FRESH and the
  task silently AWAITING_MERGE with an outdated review.
- **Why:** the check requires git, and D12 keeps git out of the product;
  per the D12/D14 precedent, the actor determines the layer.
- **Smallest change:** /work's AWAITING_MERGE stop mechanically compares
  the review's diff pin against the current tree hash and warns +
  offers /review on mismatch. Documented in docs/state-machine.md.
- **Why not architectural:** no product change; a documented gap between
  D5's intent and the validator's scope is closed at the layer that owns
  git. Pre-registered upgrade if runtime checking proves unreliable:
  `pipeline validate --diff-hash <h>` (hash as input; git stays outside)
  — Tier 1 when a grounding instance appears.

## D16 — a git object reference is not a content hash (Tier 1)

- **Problem:** the Review shim wrote the diff pin as
  `sha256:$(git rev-parse HEAD^{tree})`, but a git tree id is 40 hex on a
  sha1 repository and the validator applied `^sha256:[0-9a-f]{64}$` to
  *every* pin. The first real review on a default git repo would therefore
  be INVALID with `hash-format` — a violation the reviewer cannot fix,
  because the instruction was what was wrong. It stayed invisible because
  the fixture hardcoded a synthetic 64-hex constant: the one place where
  fixtures-as-executable-specification had a hole, since no fixture ever
  exercised a real tree id.
- **Why:** the two identities are genuinely different. A content pin
  identifies bytes by their hash; a virtual pin identifies a git object.
  Forcing one representation onto both was the modelling error. Hashing an
  already-stable identifier merely to satisfy the older rule would have
  preserved the error and destroyed the legibility that D15's runtime
  comparison depends on.
- **Smallest change:** `REF_PREFIXES` in schemas.py declares the two
  formats (data, not logic); `hash-format` selects its pattern by whether
  the pinned artifact is virtual; `frontmatter --pin` passes an
  already-formed reference through instead of treating it as a path; the
  Review shim writes `git:<tree-id>` verbatim. `scripts/regen_fixtures.py`
  now derives the pin from a real throwaway git repository — a tree object
  is a pure function of its entries, so the fixture stays byte-stable, and
  `--object-format` is pinned so contributor git config cannot move it.
  Both mock producers take the reference from that fixture, so exactly one
  place derives a real one.
- **Why not architectural:** no schema, gate, status, contract, or enum
  changed; one rule's accepted format was corrected and one dev script
  stopped faking its input. **No PIPELINE_VERSION bump:** the change cannot
  break a previously-valid artifact, because a real git tree id never
  satisfied the old rule — the only artifact affected is the fixture, which
  regenerates in the same commit.

## D17 — verification is a decision record, not an artifact (Tier 1)

- **Problem:** "it works" was only ever an assertion. The plan's `verify:`
  lines name a verification method, but nothing recorded that the method
  *ran* or what it returned, and a sub-threshold task carried no
  verification obligation at all.
- **Why:** a decision record rather than a seventh artifact, because the
  decision log's stated purpose is the facts *not derivable from
  artifacts*, and "a check ran against this tree and reached a judgment" is
  exactly that — the same category as `merged`. A `verification` artifact
  would also break the registry's one-terminal invariant unless `review`
  consumed it, which would change `review.consumes_spec`, break
  contract-text parity, invalidate every existing review, and force
  PIPELINE_VERSION 2 for a record that is not part of the chain's
  derivation. Provenance is kept by anchoring: the record pins `tree_ref`
  in D16's `git:` form — the same reference `review.md` pins as `diff` — so
  both are tied to the same tree without a direct pin between them, and the
  fixture demonstrates it by deriving one reference and using it twice.
  *Pre-registered upgrade* if that indirection proves insufficient: promote
  to a pinned artifact at PIPELINE_VERSION 2 (the D15 pattern).
- **Smallest change:** one decision type, one command
  (`pipeline verify`), one telemetry metric. The record is a stable public
  contract, deliberately not pytest-shaped — every field is answerable by
  any verifier: `verifier` (open slug, so adding lint, security,
  performance, or migration checks never requires a product change),
  `tool` (with version, for reproducibility), `predicate` (the claim
  tested), `verdict` (closed enum — the outcome vocabulary is universal and
  small), `tree_ref`, `evidence_hash`, `standard_touched`. Three shape
  choices worth recording:
  - No `exit_code`: a process detail. The runtime interprets its own tools
    and records the meaning; `verdict` is the generalised exit code, and an
    API-based checker has no exit code at all.
  - `inconclusive` is not failure. A scanner that timed out or a benchmark
    too noisy to call must be recordable without asserting either result —
    otherwise flaky checks get written down as passes.
  - `standard_touched` generalises "did this diff add its own tests" to
    "did this diff move the bar this verifier judges by" (tests for
    `tests`, rules for `lint`, allowlists for `security`). An agent that
    changes the standard and then clears it is a different evidential
    situation, and this field is the only way telemetry can see it, since
    the product never parses the evidence blob.
  The verdict is supplied by the runtime, so this joins D7 (consent
  authenticity) and D15 (diff currency) as an explicit runtime trust
  boundary: a broken or dishonest runtime can record `pass` for a failing
  check. Recording `exit_code` instead would not help — that number is
  equally supplied. `evidence_hash` is the mitigation: the raw output is
  pinned, so a human or a later audit can check the claim.
- **Why not architectural:** additive and inert. No schema, gate, status,
  contract, or artifact changed, and PIPELINE_VERSION is unchanged.
  **Nothing consumes the record yet** — a regression test pins that a task
  still reaches AWAITING_MERGE without one, so Phase 3a making it mandatory
  is a deliberate, visible flip rather than an accident.

## D18 — the floor is computed, not proposed (Tier 1)

- **Problem:** the entry threshold was prose in contracts/intent.md
  ("single-file fixes, doc/copy changes, mechanical renames") judged by the
  same agent that benefits from judging it low. Whatever replaces `bypass`
  needs a minimum that the agent cannot argue with, or the cheap lane
  becomes the same hole with a better name.
- **Why:** an agent must not be able to lower its own oversight. That
  requires the minimum to be a *function*, not a judgment — and one whose
  inputs the agent does not author. So the runtime supplies facts (it owns
  git, D12) and the product computes the floor from them plus repo policy.
  Because both are data, a floor is reproducible: any historical task can
  be re-judged under today's policy, which is how the policy gets
  calibrated rather than merely asserted.
- **Smallest change:** one pure module (`pipeline/floor.py`), one query
  command (`pipeline floor`), one config block, one ordering helper. Four
  choices worth recording:
  - **Fail-safe in one direction only.** No `floor:` block, no supplied
    paths, or an unmeasured extent all yield `full`. A floor that failed
    toward less process would be worse than no floor: it would look like a
    control while granting the cheap lane by accident. A fresh repo is
    therefore safe, not accidentally cheap, and `pipeline init` ships a
    starter policy so the friction is one-time.
  - **Two facts, both reliably computable:** `changed_paths` and
    `lines_changed`. `public_interface_delta` was considered and rejected
    for now — it needs LSP/AST work the runtime cannot yet do reliably, and
    *a fact that defaults to false is a fact that silently lowers the
    floor*. Fewer facts, all trustworthy, beats more facts with a false
    negative in them. Pre-registered as an additive fact when the runtime
    can compute it.
  - **Lanes are a product enum.** `LANES = ("express", "full")`, ordered.
    The earlier design kept lane names entirely in the runtime, but Phase 3b
    must enforce "the chosen lane is at or above the floor", and an ordering
    cannot be enforced over a vocabulary the product does not hold. Only the
    *ordering* is product truth; which obligations each lane implies stays
    runtime policy. `at_or_above` rejects unknown names rather than ordering
    them, so a typo can never satisfy a floor.
  - **Own glob translation, not fnmatch.** In fnmatch `*` crosses `/`, so a
    pattern like `*.md` would silently match every markdown file in the tree
    and force every task to `full` — a policy file that means something
    other than it reads is unacceptable for a security-relevant list. Here
    `*` stays within a segment and `**` spans segments, as in gitignore.
  - Every `full` verdict carries its reasons, and *all* independent causes
    are reported rather than the first to fire. A floor nobody can explain
    is a floor nobody will trust when it says no.
- **Why not architectural:** additive and inert. The floor influences
  nothing — no status, gate, contract, artifact, or enum consults it; the
  command is a query and always exits 0. Phase 3b is where a disposition
  records a lane and the ordering is enforced. PIPELINE_VERSION unchanged.

## D19 — the merge gate requires a passing verification (Tier 2)

- **Problem:** "it works" was never checked by the state machine. A task
  reached AWAITING_MERGE on the strength of an approving review alone, so
  the Execution Contract's G3 ("all plan verifications executed and
  passing") was an honour-system claim. D17 gave verification a record but
  deliberately consumed it nowhere; this is the flip.
  *Grounding instance:* the demonstration recorded against Phase 0 — a
  request to change a session token TTL from 24h to 720h reached a terminal
  state with no review **and no verification**, and the resulting telemetry
  record carried twelve nulls. Nothing in the product could have noticed.
- **Why:** verification is the cheapest obligation in the system and the
  only one that is machine-checkable, so it is the wrong one to leave
  optional. Making it a status rather than a validator rule follows D10's
  precedent: an explicit state beats overloading STALE or BLOCKED, and the
  condition is about the decision log rather than artifact validity, which
  is frontier's domain, not the validator's.
- **Smallest change:** one status, one guard before AWAITING_MERGE. A task
  leaves UNVERIFIED when, for every verifier that recorded against the
  **reviewed tree**, the latest record is `pass`. Four choices:
  - **Anchored to the reviewed tree, not to the task.** A verification
    whose `tree_ref` differs from the review's `diff` pin does not count —
    otherwise a stale pass from an earlier tree would open the gate. This
    is the D17 anchor doing real work rather than being decorative, and the
    fixture needed no change because it already derives one reference and
    uses it in both places.
  - **Latest per verifier, in log order.** Consistent with how escalations
    and returns are already resolved (log order, never clocks). A failure
    followed by a re-run that passes is resolved; a pass followed by a
    later failure is not.
  - **`inconclusive` is not a pass.** A checker that could not reach an
    answer holds the gate. The alternative — treating "don't know" as
    "fine" — is exactly how verification becomes theatre.
  - **UNVERIFIED is not a human stop.** The runtime resolves it by running
    the checks and recording them, so `pipeline status` exits 0 and `/work`
    can continue without interrupting anyone. Human attention is spent at
    the three consent gates, not on mechanical work.
- **Why not architectural:** the workflow, its contracts, its gates, and
  its artifacts are unchanged; one state that was implicit in the Execution
  Contract's G3 became explicit and enforced. No schema, artifact, or
  contract text changed and PIPELINE_VERSION is unchanged. Every test that
  broke was an intentional end-to-end driver (the mock agent, M5's
  acceptance path) or the deliberate inversion of D17's
  "not-yet-required" pin.

## D20 — the lane a task ran under is recorded, and overrides are countable

- **Problem:** D18 computes a floor but nothing records what was actually
  chosen, so "the agent may propose at or above the floor" was an intention
  with no representation. Worse, the floor is a *prediction*: it is computed
  from intended paths before work, and the work can wander onto a governed
  surface afterwards. Without a check against the realized diff, the cheap
  lane would be granted on a promise.
- **Why:** the original `bypass` failed not because an escape hatch existed
  but because it was invisible — self-recorded, unexplained, and carrying
  no telemetry a quarterly review could count. An escape hatch must exist,
  or people route around a system that cannot be unblocked. So the design
  goal is not to forbid a below-floor lane but to make it **loud, reasoned,
  and countable**.
- **Smallest change:** one decision type, one command pair, one telemetry
  field.
  - `disposition {lane, floor, override_reason?}`, validated on append:
    both names must be known lanes, and `override_reason` is required
    exactly when the lane is below the floor — and *rejected* otherwise, so
    a non-override can never be dressed as one. The comparator is
    `floor.at_or_above`, the single definition of the ordering.
  - `pipeline floor-check` recomputes the floor from the realized diff and
    exits 2 on a violation, naming what raised the floor and how to resolve
    it. This is what makes retroactive consent safe for the express lane in
    the next phase: a task disposed `express` that then touched `auth/**`
    is caught mechanically at the gate, not by a human noticing. A recorded
    override *clears* the gate — an escape hatch that does not open is
    decorative — but only for a realized floor no higher than the one it was
    recorded against, and the pass reports the reason rather than being
    silently green.
  - `disposition` in telemetry carries `{lane, floor, overridden}`. Shipping
    the enforcement without the measurement would repeat exactly the mistake
    being fixed.
- **Why not architectural:** additive. **Absent disposition means `full`**,
  so every existing task and test behaves precisely as before; lane
  validation on append is the only new enforcement, and the frontier is
  untouched — Phase 4 is where a lane changes which artifacts a task needs.
  No schema, artifact, contract, status, or PIPELINE_VERSION change.

## D21 — the express lane substitutes the request for intent and plan

- **Problem:** the only cheap path was `bypass`, which discarded the most
  valuable guarantee (independent adjudication) in order to avoid the most
  expensive one (human consent stops). That is inverted: adjudication is the
  one obligation whose value tracks blast radius rather than effort, and
  whose cost already scales with the diff. What was missing was a lane with
  *fewer stops* and *the same checking*.
- **Why:** the two consent gates are what cost human attention, and they are
  the only obligations that can be substituted without losing a guarantee —
  because the human's own words already exist, immutable and hash-pinned, in
  `request.md`. So `express` uses the request as the standard the review
  adjudicates against, and keeps disclosure, adjudication, and verification
  exactly as they are. One stop (merge) instead of three; nothing waived.
- **Smallest change:** `Schema.consumes_alt` (a second *accepted* pin set)
  and `LANE_CHAINS` (which artifacts a lane requires). Four choices:
  - **`consumes_alt` is a compatibility mechanism, not a second execution
    path.** The validator is file-only and cannot know a task's lane, so it
    accepts either *complete* shape and rejects any mixture; the frontier,
    which does read the decision log, decides which shape the lane in force
    permits. The same contract produces the artifact either way — the
    contract texts describe the lane difference in prose, and
    `consumes_express` in their frontmatter is parity-tested against
    `consumes_alt` so the two cannot drift.
  - **The lane parameterises the chain walk; it does not fork it.** One loop
    over `LANE_CHAINS[lane]`, defaulting to `CHAIN`. There is no
    lane-specific gate logic anywhere: gates 1 and 2 are not suppressed on
    `express`, they simply cannot fire, because their rule is about a fresh
    `intent.md`/`plan.md` and those files never exist.
  - **`express` keeps the ledger.** An earlier sketch dropped it as
    pointless without a plan to diverge from, which was wrong twice: an
    empty Entries list is a signed claim either way (here, "the diff does
    what the request asked and nothing else"), and it gives the walk an
    artifact-shaped work-done signal instead of special-casing the
    verification record as a pseudo-step. Uniformity was the deciding
    argument.
  - **Escalation is re-disposition.** A change that outgrows the lane needs
    no mechanism: recording a `full` disposition makes the walk require the
    full chain and the task resumes at REFINING. This is also what an
    express `return-to-plan` verdict means, and what E1–E4 mean on a lane
    with no planning phase.
- **Why not architectural:** no new status, gate, contract, decision type,
  or enum; `consumes_alt` defaults to None so every artifact without one is
  unchanged, and `LANE_CHAINS["full"] is CHAIN`. **No PIPELINE_VERSION
  bump:** the accepted set for every existing artifact is unchanged — the
  alternate is strictly additional, so no previously-valid artifact becomes
  invalid. A second fixture directory (`tests/fixtures/express/`) is the
  executable specification for the lane; it lives outside `happy/` because
  several test modules take `next(happy.iterdir())`.

## D22 — bypass creation is retired; the record stays readable (Tier 2)

- **Problem:** with the express lane in place, two cheap paths existed and
  one of them was strictly worse. `bypass` skipped adjudication entirely,
  was recorded by the agent itself, and produced a telemetry record of
  twelve nulls. Leaving it reachable would leave the incentive gradient
  pointing at exactly the wrong door — cost pressure widens the cheapest
  path, and the cheapest path must not be the unreviewed one.
- **Why:** the entry gate was in the wrong place *and* the wrong shape. The
  Intent Contract's typed early return classified work by prose judgment
  from the agent that benefits from judging it low; the threshold is now
  computed (D18) and disposed by a human (D20), both *before* this contract
  runs. So the dispatch does not move — it leaves the contract entirely,
  and `contracts/intent.md` now says so rather than describing a branch
  that no longer exists.
- **Smallest change:** delete the `decide bypass` subcommand and the shim
  line that invoked it; rewrite the contract's Dispatch section and set its
  `bypass:` frontmatter to false. **The decision type, the BYPASSED status,
  the frontier's clearing rule, and the telemetry outcome all stay.**
  Decisions are append-only history: a log written before this change must
  still resolve, so creation is retired while the reader is kept. A test
  pins both halves — the CLI path is gone (exit 1) and a directly-appended
  historical record still resolves to BYPASSED.
- **Why not architectural:** nothing in the state machine changed; one
  creation path was removed and one contract's prose was corrected to match
  where the entry gate actually lives. No schema, artifact, status, enum, or
  PIPELINE_VERSION change. The retired member keeps its slot in
  `DECISION_TYPES` with a comment, because removing it would break exactly
  the historical logs the append-only rule exists to protect.

## D23 — producer fusion and consent batching, rejected before implementation

Recorded per docs/governance.md: "a proposal rejected on merits records why,
so it isn't re-litigated without new grounding."

- **Problem:** the roadmap planned two runtime optimisations for the cost
  complaint that started this work — *producer fusion* (one AI pass writing
  intent, findings and plan, verified feasible: the chain validates and the
  frontier walks to gate 1) and *consent batching* (presenting intent and
  plan together, recording two hash-pinned consents from one human reply).
  Together they cut a small task from 5 producer calls and 3 stops to 3 and
  2, with no product change.
- **Why:** the express lane obsoleted both. They were designed to relieve
  medium-sized work stuck in the full pipeline, and that work now runs
  express — 2 producer calls, 1 stop — which is cheaper than fusion and
  batching would have made it. What remains on the full lane is work the
  floor judged consequential: governed surfaces, wide diffs, persisted
  shapes. For exactly that work, both optimisations are *harmful*. Gate 1
  exists to confirm the target before plan effort is spent; presenting it
  after a plan exists anchors the human to the plan, and fusing the
  producers guarantees that ordering. Applying them would trade away the
  full lane's main reason for existing to save calls on the tasks least in
  need of saving.
- **Smallest change:** none — neither was implemented. `/work` instead
  states the opposite rule ("present these gates one at a time"), and a test
  pins it so the batching idea cannot drift back in unnoticed.
- **Why not architectural:** nothing was built; scope shrank. **Kill
  criterion for the rejection:** if telemetry later shows full-lane tasks
  are dominated by cases that are consequential-but-tiny — a one-line change
  on a governed path, say — and their cost is what drives people to
  override the floor, then fusion becomes worth revisiting *for that shape
  only*. The feasibility finding above stands and need not be re-derived.

## D24 — `implement` duration is anchored to authorisation, not to the plan

- **Problem:** `duration_by_phase.implement` measured from the
  `plan_approved` timestamp, which the express lane never has. Extracting an
  express task returned four nulls and one number: three of the nulls are
  correct (those phases did not happen), but `implement` was null for a
  phase that *did* happen. The one duration measuring the work itself was
  unmeasurable on the lane the operational phase most needs to evaluate —
  and it would have failed silently, biasing every later comparison between
  the lanes after a quarter of collection.
- **Why:** the metric means one thing on every lane — *time spent
  implementing after work was authorised.* The authorising event differs
  (plan approval on `full`, the disposition on `express`, since choosing the
  lane is what authorises execution there); the quantity does not. Anchoring
  to the plan conflated the concept with one lane's representation of it.
- **Smallest change:** the `implement` start anchor falls back
  plan_approved -> disposition -> plan.produced_at. Most specific
  authorisation first, so a full-lane task with a disposition recorded still
  measures from its plan approval.
- **Why not architectural:** an instrumentation defect, not a model change.
  No schema, artifact, contract, status, decision type, or
  PIPELINE_VERSION change; one metric now computes on both lanes instead of
  one. Found by extracting the express fixture rather than by reading the
  code — the value of running the measurement before trusting it.

## D25 — the shipped floor policy matches at any depth (Tier 1)

- **Problem:** the starter `governed_paths` were root-anchored — `auth/**`,
  `migrations/**`, `package.json`. Replayed against realistic layouts, the
  shipped policy governed **nothing**: `src/auth/session.py`,
  `db/migrations/0007.sql` and `packages/api/package.json` were all
  express-eligible. Only a repository that happens to keep `auth/` at its
  root got any protection at all.
- **Why:** this is the fail-safe direction inverted. D18's guarantee is that
  every unknown *raises* the floor, but a governed pattern that silently
  matches nothing *lowers* it — and does so while looking like a control. A
  one-line change to a session token under `src/auth/` would have been
  granted the express lane by a policy that appears to forbid exactly that.
  Worse, it fails quietly: nothing errors, no query shows it, and the only
  symptom is an express rate that looks encouragingly high.
- **Smallest change:** make the patterns depth-independent (`**/auth/**`),
  using the glob semantics D18 already defined; add `**/secrets/**`. Two
  patterns stay root-anchored deliberately — `.github/**` and
  `.dev/config.yaml` are required to live there. A parametrised test pins
  ten realistic paths as governed, and a counterweight test pins ordinary
  source and docs as still express-eligible, because a policy that governs
  everything makes the cheap lane inert — the opposite failure.
- **Why not architectural:** policy data, not product logic. No schema,
  artifact, contract, status, enum, or PIPELINE_VERSION change; the floor
  algorithm is untouched. This is the calibration pass the operational phase
  begins with, and it tunes an obvious false negative rather than aiming at
  a target express rate — which would be fitting policy to a number instead
  of to risk.

## D26 — RETURNED never cleared on same-day regeneration (Tier 1)

- **Problem:** discovered during real usage of the tool — bootstrapping an
  unrelated downstream project — not by inspection. D11's clearing rule
  compares a target artifact's `produced_at` against the routing decision's
  `ts` lexically. `produced_at` is written as an ISO-8601-looking scalar,
  but PyYAML's implicit resolver auto-parses that shape into a `datetime`
  on every load — every artifact ever produced is subject to this, not
  only ones passed through the CLI. `str()` on that object formats as
  `'... HH:MM:SS+00:00'` (space, offset), never the decision log's
  `'...THH:MM:SSZ'`. The space byte sorts before `'T'`, so any same-day
  comparison concluded "not yet produced" regardless of actual
  chronology — the overwhelmingly common case for a return-then-fix cycle,
  since escalation and repair normally happen the same day.
  Reproduced directly: `str(produced_at) <= routed.ts` evaluated `True`
  for a plan regenerated at 11:30 against a decision at 11:05 — the wrong
  answer, in the direction that leaves a task stuck.
- **Why the existing test didn't catch it:**
  `test_state_RETURNED_by_decision_and_clearing`'s `consent_all()` helper
  deletes `decisions.jsonl` entirely and re-appends only the two gate
  consents, erasing the `escalation` and `returned` decisions the test had
  just appended. By the time the final assertion runs, RETURNED precedence
  never fires at all — the test passes via the ordinary chain-walk
  fallback, not via D11's comparison. The assertion was correct; the
  reason it passed was not what the test's comment claimed.
- **Why:** the model (D11's rule) is correct and unchanged — lexical
  comparison of ISO-8601 strings is fine. The implementation didn't guard
  against YAML's implicit typing silently producing a different string
  shape than the one being compared against.
- **Smallest change:** `_produced_at()` normalizes a `datetime` value back
  to the canonical `%Y-%m-%dT%H:%M:%SZ` shape before returning — the one
  call site of the affected comparison. `telemetry.py`'s `_parse_ts`
  already handled both input types correctly for the same underlying
  reason; this brings `frontier.py` in line with that. The existing test's
  misleading comment is corrected to describe what it actually verifies
  (the decisions-reset fallback), and a new test
  (`..._only_clears_on_genuine_regeneration`) exercises the real mechanism
  end to end: the `returned` decision stays in the log throughout, a
  same-day regeneration *before* the decision correctly stays RETURNED,
  and one strictly *after* it correctly clears — proving discrimination,
  not just "always clears now."
- **Why not architectural:** no schema, artifact, contract, status,
  decision type, or PIPELINE_VERSION change; one function's output is
  normalized to the format its caller already assumed. **This same fix is
  also landed independently as D16 on `fix/d11-produced-at-datetime-
  coercion`, branched off `master`** — the bug predates the D17–D25 work
  on this branch and is not specific to it; it is applied here too because
  this branch is the code actually running for downstream usage while it
  remains unmerged. The two branches will need their D-numbering
  reconciled at whichever merge lands first; the fix itself is identical.

## D27 — telemetry rejects a negative phase duration as invalid, not small (Tier 1)

- **Problem:** discovered downstream, in the benchmark application's second
  merged task — `duration_by_phase.review` extracted as `-19292`. Root
  cause: a hand-authored `ledger.md` `produced_at` was stamped with the
  agent's local wall-clock reading (`09:45:00`) but suffixed `+00:00` as if
  it were already UTC, landing chronologically after `review.md`'s
  correctly-stamped `produced_at`. `_seconds()` computed `review.produced_at
  - ledger.produced_at` and returned the negative result verbatim — no
  check anywhere rejects a phase that finishes before it starts.
- **Why:** this is not D16/D26 again — those were parsing bugs; a syntactically
  ambiguous or PyYAML-retyped value compared incorrectly. This value parsed
  exactly as written and was internally consistent (a real, well-formed
  timestamp, just describing the wrong instant). Three distinct temporal
  failure modes have now surfaced in this pipeline — datetime
  representation (D11/D16/D26), timezone authoring (this bug), and telemetry
  invariant validation (the gap this decision closes) — independent enough
  that their existence argues the pipeline is surfacing distinct edge cases
  rather than repeatedly hitting one underlying design flaw.
- **Smallest change:** `_seconds()` treats a negative delta as invalid input,
  not a small measurement — it emits `None` (the metric's existing
  "cannot be computed" contract, unchanged) and raises a `UserWarning`
  naming the task and phase, then extraction continues; one invalid phase
  never blocks the rest of the record. No new schema field: the warning is
  a side-channel diagnostic (Python's stdlib `warnings`), not a change to
  the deterministic, wall-clock-free record shape golden-tested elsewhere.
  A new test constructs the exact failure shape (a fixture's `ledger.md`
  pushed past its `review.md`) and asserts both the `None` and the warning.
- **Why not architectural:** no schema, artifact, contract, status, decision
  type, or `PIPELINE_VERSION` change; one helper gains an invariant check
  it should have had from the start. The upstream authoring mistake itself
  is corrected in the downstream repository's own history, not here — this
  decision only hardens the pipeline against a class of bad input it
  cannot prevent (an agent's own timestamp arithmetic), only detect.

## D28 — artifact-authoring mechanics are part of the contract surface (Tier 1)

- **Problem:** discovered by instrumenting six independent benchmark runs that
  drove the pipeline through real work (two lanes × the same defect, plus four
  full-lane feature runs). Three defects recurred in *every* run, none of them
  about the pipeline model — all about the mechanics of producing an artifact.
  (1) `pipeline frontmatter --pin` refuses a file with no `---` fence, while
  the contract skills direct the author to write the body first and set
  frontmatter only through that command: the one command that exists to keep
  hands off frontmatter could not bootstrap the frontmatter it required, so
  every artifact in every run cost a failed invocation plus a hand-written
  fence. (2) `tagged-assumptions`/`tagged-questions` matched `- [verified]`
  as a literal prefix, but `contracts/findings.md` renders the tags decorated;
  an author following the contract's own typography produced `INVALID`, and
  the violation quoted the offending line without naming the expected form, so
  diagnosis required reading `validate.py`. (3) `verdict-enum` compared the
  whole `## Verdict` section body against the enum, so a backticked token was
  unparseable. Two independent agents lost a correction round to (2); one
  moved its rationale to a different heading to work around (3).
- **Why:** these are not the pipeline being strict, they are the pipeline
  disagreeing with its own documentation. Strictness that an author cannot
  satisfy by reading the contract is a defect in the contract surface, and it
  taxes exactly the artifacts the governance model depends on being written.
  The tag and the verdict are the contract; their markdown styling is not.
- **Smallest change:** `--init` on `frontmatter` creates the fence when absent
  and preserves the body verbatim — opt-in, so the prior refusal stands
  unchanged for every existing caller, and that refusal now names `--init` as
  its fix. Two validator helpers, `_undecorate()` and `_head_tag()`, ignore
  markdown emphasis around a token; the two untagged-* violations now state the
  legal tags, and `verdict-invalid` states that the section holds the bare
  token and rationale belongs elsewhere. Five tests: three failing-first in
  `test_validate.py`, two in `test_decisions_cli.py` (one covering `--init`,
  one pinning that the un-flagged path still refuses and self-diagnoses).
- **Why not architectural:** no schema, artifact, contract text, status,
  decision type, gate, lane, or `PIPELINE_VERSION` change. `contracts/` is
  untouched — fixing the validator is what makes the documentation correct,
  rather than editing the documentation to match a validator that was wrong.
  Every change is additive and backward compatible: previously valid documents
  stay valid, previously rejected ones are a strict subset of what was rejected
  before.

## D29 — `status` exit 3 is contract, not a bug (Tier 0, no code change)

- **Problem:** the same benchmark runs reported `pipeline status` "exiting
  nonzero on a healthy task" as a defect, and one run additionally reported
  `pipeline validate` doing the same. Both were escalated as candidates for a
  compatibility decision about changing the exit codes.
- **Why:** the first is documented behavior and the second is not real.
  `docs/cli.md` §Exit codes already defines `3 needs-human (blocked or awaiting
  a consent gate)`, and `_status_exit` implements exactly that; a caller can
  branch on it, which is more useful than a bare 0. `validate` returns `OK`
  when `is_valid` — verified empirically; the claim was mistaken and was
  withdrawn by the agent that made it after isolating the exit code. Nothing
  to decide: changing either would break a documented contract to accommodate
  callers who chained commands under `set -e` without reading the contract.
- **Smallest change:** none to the product. The gap is discoverability, so the
  pitfall list in `AGENTS.md` now states that a nonzero exit is often a status,
  not a failure, and points at `docs/cli.md`.
- **Why not architectural:** no product bytes changed. Recorded so the question
  is not re-litigated the next time an agent's shell pipeline breaks at a gate.

## D30 — the core travels with its invoker: path invocation, stdlib only (Tier 2)

- **Problem:** every runtime binding shelled out to an installed `pipeline`
  binary. The dependency was never the code — it was the installation: a
  PATH entry, a pip-installed PyYAML, and venv visibility, none of which a
  Claude Code session, a Codex session, or a bare CI runner controls. On a
  machine without the PATH export every slash command silently depended on
  the hooks' module-invocation fallback working from the right cwd.
- **Why:** what makes a CLI painful across agent runtimes is provisioning,
  not executing. The fix is code that travels with the thing that invokes
  it. Prose reimplementation was rejected — canonicalization (line endings,
  key order, folding) reconstructed from instructions fails silently, and
  a deterministic floor policy cannot be "approximately" followed. Inline
  one-liners were rejected — code that cannot be tested or diffed as a
  unit, plus real logic never fits one line. What remains is the same
  audited package, repackaged so nothing needs installing.
- **Smallest change:** (1) `pipeline_cli.py` at the repo root — the sole
  entry point; self-locating via `realpath(__file__)`, asserts Python
  ≥ 3.9 with a readable message *before* importing the package, exit-code
  contract unchanged (incl. exit-3 gates, D29). `install.sh` symlinks the
  repo to `~/.claude/pipeline/core`; the canonical invocation everywhere is
  `python3 ~/.claude/pipeline/core/pipeline_cli.py <cmd>`; hooks and
  foreign runtimes resolve `$CONTRACT_RUNTIME` first. The `bin/` PATH shim
  is retired. (2) PyYAML replaced by `pipeline/miniyaml.py`, a restricted
  subset parser + canonical dumper: block/flow mappings and sequences as
  the artifacts actually use them, quoted/plain scalars, comments,
  continuation-line folding; anything outside the subset raises typed with
  a line number. Two deliberate divergences: timestamps and floats stay
  plain strings — which retires the D26 bug class at the parser (D26's
  normalization is kept for artifacts already written by PyYAML, its rule
  unchanged, its mechanism now string-based). Dump style: insertion order,
  no line wrapping; safe because hashing is over exact file bytes and
  fixtures regenerate byte-identically. (3) `scripts/selftest.py` — a
  stdlib-only, no-pytest deployment acceptance run on any fresh clone,
  proving hash/frontier/floor/telemetry determinism against frozen goldens
  under any Python ≥ 3.9. Telemetry semantics untouched: a local
  append-only JSONL; nothing leaves the machine.
- **Why not architectural:** the boundary this repo is built on — product
  derives, runtime orchestrates (D9, D12/D14) — is exactly what survives.
  No module's logic changed; the validator, frontier, floor, and telemetry
  are byte-for-byte in behavior (339 tests green, fixture regeneration
  byte-identical). Only the *packaging* of the product's first public
  interface changed, and D18's guarantee is strengthened in passing: the
  floor function now runs from a checkout the agent can inspect but not
  provision, with zero third-party surface underneath it.

## D31 — runtime commands claim a namespace: `/pipeline-*` (Tier 0, runtime only)

- **Problem:** the Claude Code binding installed its commands as `/work`,
  `/plan`, `/review`, `/task`, `/status`, `/verify` — six of the most
  generic verbs in any agent setup. On a machine that also installs other
  skill suites (observed live: gstack's `/plan`, `/review`, `/ship`
  family), whichever install ran last owned the name, and the loser failed
  silently: a user typing `/review` could get a generic PR review where
  the pipeline's adjudicated Review Contract was required, with nothing
  recording that the wrong tool ran.
- **Why:** the collision is structural, not accidental — a shared global
  namespace (`~/.claude/commands`) and deliberately ordinary names. The
  product cannot fix it (names are runtime property, D9); politeness
  ("install this last") is not a mechanism. A prefix is: `/pipeline-work`
  cannot be claimed by an unrelated suite by accident.
- **Smallest change:** rename the twelve command files to
  `pipeline-<name>.md` and update every cross-reference in the runtime,
  docs, and binding tests. `install.sh` additionally removes stale
  unprefixed links that point into this checkout (or a pre-rename
  contract-pipeline one), so an upgrade leaves no shadowing residue.
  Skills (`intent-contract`, …) and the reviewer agent already carried
  distinctive names and are unchanged. Zero product bytes changed.
- **Why not architectural:** the boundary is untouched — this is the
  runtime renaming its own surface. Historical documents (this log,
  CHANGELOG history) keep the old names; they were true when written.

## D32 — the project is named reins (Tier 0, no behavior change)

- **Problem:** the port (D30) shipped under the placeholder name
  contract-runtime — accurate but generic, and one methodology-word away
  from the contract-pipeline repo it superseded. Candidate names that
  leaned on task-pipeline vocabulary (`dev`, `dev-skills`, `squad`)
  were rejected for the same reason the D31 rename happened: `squad` is
  already a live task-pipeline suite on the reference machine, and
  generic names lose silently in shared namespaces.
- **Why:** *reins* names the actual design: the agent does the running,
  the human holds the reins, and the gates are rein-pulls. It is short,
  collision-free in the observed environment, and describes governance
  rather than tooling.
- **Smallest change:** repo renamed to `hashirventhodi/reins` (GitHub
  redirects the old URLs); local checkout at `~/Code/tools/reins`; the
  hook/CI env override `$CONTRACT_RUNTIME` is now `$REINS_HOME` (D30's
  text names the old variable — true when written, superseded here).
  The canonical invocation path `~/.claude/pipeline/core/pipeline_cli.py`
  and the `/pipeline-*` command namespace (D31) are deliberately
  unchanged: they name the *pipeline* concept, not the project, and
  renaming them would churn every binding for zero collision benefit.
- **Why not architectural:** nothing executes differently; one env-var
  spelling and display strings changed. Recorded so the name, and the
  names rejected, are not re-litigated.
