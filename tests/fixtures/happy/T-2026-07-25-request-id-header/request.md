---
task: T-2026-07-25-request-id-header
source_ref: local
created_at: 2026-07-25T09:00:00Z
---
Add a request id to every API response so support can trace user reports
to server logs. Probably a middleware? Also the logs are a mess in
general, would be nice to clean them up at some point.
