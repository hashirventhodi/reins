---
pipeline: 1
contract: findings
task: 001-request-id-header
produced_at: 2026-07-25T09:12:00Z
consumes:
- artifact: request
  hash: sha256:066c768145ac8ee82d066eec752b2ce12f09ef1c5987f993fccc1cd4c9b450e1
- artifact: intent
  hash: sha256:35fdc028aa6ea0304255fac14ab6df9df3e23b7546b7c88e965e45efcda39de3
---
# Findings — request id tracing

## Scope statement
Determine how the API service can attach a per-request identifier to
responses and to every log line emitted while handling that request, per
the confirmed intent.

## Current state
- HTTP handling is centralized in a middleware stack (src/api/app.py:41).
- Logging uses the stdlib logging module with a shared formatter
  (src/api/logging.py:17); no per-request context is bound today.
- An X-Request-Id inbound header is already read but discarded by the
  proxy shim (src/api/proxy.py:88).
- Response tests assert exact header sets in three places
  (tests/api/test_headers.py:23).

## Constraints
- Public API responses are additive-only per AGENTS.md decision "public
  API backward compatibility" (AGENTS.md).
- Log format changes must keep the ingestion pipeline's line grammar
  (docs/ops/log-grammar.md).

## Assumptions
- [verified] The middleware stack wraps all public routes
  (src/api/app.py:41).
- [unverified] The ingestion pipeline tolerates one additional key=value
  pair per line.

## Open questions
- [non-blocking] Should inbound X-Request-Id be trusted when present, or
  always re-generated?

## Out-of-scope observations
- Logging configuration is duplicated between app startup and worker
  startup (src/api/logging.py:17, src/worker/boot.py:9) — cleanup
  candidate, deferred per intent non-goals.
