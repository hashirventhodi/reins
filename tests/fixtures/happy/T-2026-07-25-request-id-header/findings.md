---
pipeline: 1
contract: findings
task: T-2026-07-25-request-id-header
produced_at: 2026-07-25T09:12:00Z
consumes:
- artifact: request
  hash: sha256:670de3bce842994df4985d0cb623032589f234436782139368ea455b05f284a5
- artifact: intent
  hash: sha256:3572fb1e77fcada4dd818311dde7d74c63845b0628166a4c0ba463002c24024a
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
