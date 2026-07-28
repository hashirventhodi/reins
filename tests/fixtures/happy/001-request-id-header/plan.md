---
pipeline: 1
contract: planning
task: 001-request-id-header
produced_at: 2026-07-25T09:20:00Z
consumes:
- artifact: intent
  hash: sha256:35fdc028aa6ea0304255fac14ab6df9df3e23b7546b7c88e965e45efcda39de3
- artifact: findings
  hash: sha256:168c4dda0e127db63eaa000e27bbe25f2fe08f8581694f759500f4acba6b6366
---
# Plan — request id tracing

## Objective & acceptance criteria
Attach a per-request id to every public API response and bind it to all
log lines emitted during handling.
- AC1: every 2xx-5xx response carries X-Request-Id
  (verify: tests/api/test_request_id.py::test_header_present).
- AC2: every log line emitted during a request contains request_id=<id>
  (verify: tests/api/test_request_id.py::test_log_binding).
- AC3: existing header assertions updated additively, no removals
  (verify: pytest tests/api/test_headers.py).

## Steps
1. Add RequestId middleware generating a uuid4 per request.
   verify: tests/api/test_request_id.py::test_header_present
2. Bind the id into a logging contextvar and extend the formatter with a
   trailing request_id=<id> pair.
   verify: tests/api/test_request_id.py::test_log_binding
3. Update header-set assertions additively.
   verify: pytest tests/api/test_headers.py

## Test strategy
New tests for AC1/AC2; existing header tests cover regression surface.
Consciously untested: none.

## Reversibility
Middleware removal restores prior behavior; the formatter change is a
trailing additive pair. No irreversible steps.

## Risks
- Ingestion tolerance for the added pair is [unverified] — mitigation:
  step 2 conforms to docs/ops/log-grammar.md and adds the pair last.
- Inbound X-Request-Id trust question is open (non-blocking) — plan
  always re-generates; revisit if support workflows need propagation.

## Out of scope
- Trusting/propagating inbound X-Request-Id.
- Worker-process log binding.
- Any log cleanup (per intent non-goals).

## Checkpoints
None (no irreversible steps).
