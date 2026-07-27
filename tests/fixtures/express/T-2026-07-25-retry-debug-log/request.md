---
task: T-2026-07-25-retry-debug-log
source_ref: local
created_at: 2026-07-25T09:00:00Z
---
Add a debug log line when the retry loop gives up, so we can tell an
exhausted retry apart from a first-attempt failure in the logs.
