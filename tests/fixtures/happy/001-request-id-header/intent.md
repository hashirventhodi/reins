---
pipeline: 1
contract: intent
task: 001-request-id-header
produced_at: 2026-07-25T09:05:00Z
consumes:
- artifact: request
  hash: sha256:066c768145ac8ee82d066eec752b2ce12f09ef1c5987f993fccc1cd4c9b450e1
---
# Intent — request id tracing

## Problem statement
Support cannot correlate a user-reported failure with the server-side log
lines that produced it; triage requires guessing by timestamp.

## Goals
- Every API response is traceable to the exact log lines of its handling.
- Support can perform the correlation with information visible to the
  end user (e.g. an error page or response header they can quote).

## Success criteria
- Given a response a user reports, support locates all related log lines
  in under a minute using only what the user can see.
- Existing API consumers observe no behavioral change beyond the additive
  header.

## Non-goals
- General log cleanup or restructuring ("logs are a mess" is explicitly
  deferred; recorded for a future task).
- Distributed tracing across services.

## Scope of intent
The public HTTP API responses and the logs of the service that renders
them; nothing beyond correlation.
