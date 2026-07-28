#!/usr/bin/env python3
"""Regenerate tests/fixtures/happy — a complete valid task directory.

Fixtures are the executable specification (blueprint §12); this script is
the single source of truth for them. Artifacts are written upstream-first
so every `consumes[]` hash is the real sha256 of the file it pins.
Deterministic output: fixed timestamps, fixed task id, LF endings.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reins.artifact import sha256, sha256_bytes  # noqa: E402
from reins.schemas import GIT_REF_PREFIX, PIPELINE_VERSION  # noqa: E402

TASK = "001-request-id-header"
DIR = ROOT / "tests" / "fixtures" / "happy" / TASK
T0 = "2026-07-25T09:00:00Z"

# The express-lane fixture lives in its own top-level directory: several
# test modules take `next(happy.iterdir())`, so a second task under happy/
# would make which fixture they load depend on filesystem order.
EXPRESS_TASK = "001-retry-debug-log"
EXPRESS_DIR = ROOT / "tests" / "fixtures" / "express" / EXPRESS_TASK


def real_git_tree_ref(content: bytes = b"MIDDLEWARE_NAME = 'request-id'\n") -> str:
    """A real git tree id, so the executable specification exercises the

    same reference shape production does (D16) rather than a synthetic
    64-hex constant that only a content hash could ever have.

    Deterministic by construction: a tree object is a pure function of its
    entries — no author, message, or timestamp participates — and
    --object-format is pinned so a contributor's git config cannot change
    the fixture bytes. Shelling out to git is fine here: this is a dev
    script, not the product, which stays git-free (D12).
    """
    with tempfile.TemporaryDirectory() as tmp:
        def git(*args: str) -> str:
            return subprocess.run(("git",) + args, cwd=tmp, check=True,
                                  capture_output=True, text=True).stdout
        git("init", "-q", "--object-format=sha1", ".")
        src = Path(tmp) / "src" / "api"
        src.mkdir(parents=True)
        (src / "request_id.py").write_bytes(content)
        git("add", "-f", "-A")          # -f: ignore any global excludesFile
        return GIT_REF_PREFIX + git("write-tree").strip()


def fm(contract: str, consumes: list[tuple[str, str]], minute: int,
       task: str = TASK) -> str:
    lines = [
        "---",
        f"pipeline: {PIPELINE_VERSION}",
        f"contract: {contract}",
        f"task: {task}",
        f"produced_at: 2026-07-25T09:{minute:02d}:00Z",
        "consumes:",
    ]
    for artifact, digest in consumes:
        lines += [f"- artifact: {artifact}", f"  hash: {digest}"]
    lines.append("---")
    return "\n".join(lines) + "\n"


def write(name: str, text: str, directory: Path | None = None) -> Path:
    path = (directory or DIR) / name
    path.write_bytes(text.encode("utf-8"))
    return path


def main() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    for old in DIR.glob("*.md"):
        old.unlink()
    (DIR / "decisions.jsonl").unlink(missing_ok=True)

    request = write(
        "request.md",
        f"""---
task: {TASK}
title: Add a request id header to every API response
source_ref: local
created_at: {T0}
---
Add a request id to every API response so support can trace user reports
to server logs. Probably a middleware? Also the logs are a mess in
general, would be nice to clean them up at some point.
""",
    )

    intent = write(
        "intent.md",
        fm("intent", [("request", sha256(request))], 5)
        + """# Intent — request id tracing

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
""",
    )

    findings = write(
        "findings.md",
        fm("findings", [("request", sha256(request)), ("intent", sha256(intent))], 12)
        + """# Findings — request id tracing

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
""",
    )

    plan = write(
        "plan.md",
        fm("planning", [("intent", sha256(intent)), ("findings", sha256(findings))], 20)
        + """# Plan — request id tracing

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
""",
    )

    ledger = write(
        "ledger.md",
        fm("execution", [("plan", sha256(plan))], 41)
        + """# Deviation ledger — request id tracing

## Entries
```yaml
- step: "2"
  what: bound the contextvar in the middleware rather than a separate
    logging filter module
  why: the filter-module split added a file for six lines; middleware
    placement keeps generation and binding adjacent
  plan_impact: none
  status: within-autonomy
```
""",
    )

    # One tree reference, used by both the review's diff pin and the
    # verification record: the two are anchored to the same tree, which is
    # how a decision-log verification stays tied to what was reviewed (D17).
    tree_ref = real_git_tree_ref()

    write(
        "review.md",
        fm(
            "review",
            [
                ("intent", sha256(intent)),
                ("plan", sha256(plan)),
                ("ledger", sha256(ledger)),
                ("diff", tree_ref),
            ],
            55,
        )
        + """# Review — request id tracing

## Fidelity
The diff executes the approved plan: all three steps present, each
verification passing. Ledger entry 1 (contextvar bound in middleware) is
justified — placement is a mechanical choice the plan did not constrain,
within autonomy boundaries.
undeclared_deviations: none

## Findings
- should-fix: src/api/middleware/request_id.py:27 — uuid4 generated even
  for 404 short-circuit path; hoist above the router guard so AC1 holds
  for unrouted paths. Suggested fix: move id assignment to the first
  middleware frame.
- nit: tests/api/test_request_id.py:41 — assertion message omits the
  observed header set; include it for faster failure triage.

## Coverage
Checked: middleware ordering against src/api/app.py stack; formatter
change against docs/ops/log-grammar.md line grammar; additive-only edits
to tests/api/test_headers.py; absence of scope creep in src/api/logging.py
(no cleanup performed, per plan out-of-scope); dependency manifests
untouched (no E2-class changes).

## Verdict
approve-with-fixes
""",
    )

    print(f"regenerated {DIR}")

    from reins import decisions as dec

    dec.append(DIR, dec.make(
        "intent_confirmed", "2026-07-25T09:07:00Z",
        intent_hash=sha256(intent), edited=False))
    dec.append(DIR, dec.make(
        "plan_approved", "2026-07-25T09:24:00Z",
        plan_hash=sha256(plan), edited=True))
    dec.append(DIR, dec.make(
        "verification", "2026-07-25T09:45:00Z",
        verifier="tests", tool="pytest 9.1.1",
        predicate="plan verifications for AC1-AC3 pass",
        verdict="pass", tree_ref=tree_ref,
        evidence_hash=sha256_bytes(
            b"tests/api/test_request_id.py::test_header_present PASSED\n"
            b"tests/api/test_request_id.py::test_log_binding PASSED\n"
            b"tests/api/test_headers.py PASSED\n"),
        standard_touched=True))   # the diff adds its own tests (plan step 1-3)
    print("wrote decisions.jsonl (2 consents, 1 verification)")


def express() -> None:
    """The express-lane fixture (D21): the cheapest path that still

    discloses and adjudicates. Two artifacts, one human stop (merge).
    Gates 1 and 2 cannot fire because intent.md and plan.md never exist —
    the immutable request is the standard the review adjudicates against.
    """
    from reins import decisions as dec

    EXPRESS_DIR.mkdir(parents=True, exist_ok=True)
    for old in EXPRESS_DIR.glob("*.md"):
        old.unlink()
    (EXPRESS_DIR / "decisions.jsonl").unlink(missing_ok=True)

    tree_ref = real_git_tree_ref(b"RETRY_EXHAUSTED = 'giving up after %d tries'\n")

    request = write("request.md", f"""---
task: {EXPRESS_TASK}
title: Log when the retry loop gives up
source_ref: local
created_at: {T0}
---
Add a debug log line when the retry loop gives up, so we can tell an
exhausted retry apart from a first-attempt failure in the logs.
""", EXPRESS_DIR)

    ledger = write(
        "ledger.md",
        fm("execution", [("request", sha256(request))], 12, EXPRESS_TASK)
        + """# Deviation ledger — retry exhaustion log line

## Entries
```yaml
[]
```
""",
        EXPRESS_DIR,
    )

    write(
        "review.md",
        fm("review",
           [("request", sha256(request)), ("ledger", sha256(ledger)),
            ("diff", tree_ref)],
           20, EXPRESS_TASK)
        + """# Review — retry exhaustion log line

## Fidelity
The request asked for one debug line distinguishing retry exhaustion from a
first-attempt failure; the diff adds exactly that on the exhaustion branch
and nothing else. The empty ledger claims the diff matches the request, and
that claim holds: no other file, symbol, or behaviour is touched.
undeclared_deviations: none

## Findings
- nit: src/api/retry.py:88 — the message interpolates the attempt count but
  not the elapsed time; elapsed would make the line more useful. Suggested
  fix: include the loop's own duration if it is already tracked.

## Coverage
Checked: the exhaustion branch is the only new call site (src/api/retry.py:88);
log level matches the surrounding calls; no change to retry counts, backoff,
or control flow; no new imports; dependency manifests untouched.

## Verdict
approve
""",
        EXPRESS_DIR,
    )

    dec.append(EXPRESS_DIR, dec.make(
        "disposition", "2026-07-25T09:05:00Z", lane="express", floor="express"))
    dec.append(EXPRESS_DIR, dec.make(
        "verification", "2026-07-25T09:16:00Z",
        verifier="tests", tool="pytest 9.1.1",
        predicate="the suite passes and the new line is asserted",
        verdict="pass", tree_ref=tree_ref,
        evidence_hash=sha256_bytes(
            b"tests/api/test_retry.py::test_exhaustion_logs PASSED\n"),
        standard_touched=True))
    print(f"regenerated {EXPRESS_DIR} (disposition + verification)")


if __name__ == "__main__":
    main()
    express()
