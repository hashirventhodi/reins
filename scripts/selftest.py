#!/usr/bin/env python3
"""Fresh-clone determinism self-test (D30). Stdlib only, no pytest.

    python3 scripts/selftest.py            # run all checks
    python3 scripts/selftest.py --regen    # refreeze scripts/goldens/

The pytest suite is the development acceptance; this script is the
*deployment* acceptance: it proves on any machine, from any cwd, under
any Python >= 3.9, that the deterministic core derives byte-identical
facts from the executable specifications in tests/fixtures/. Exit 0 on
success, 1 on any failure.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)

from reins import artifact, decisions, floor, frontier  # noqa: E402
from reins import miniyaml, telemetry, validate  # noqa: E402
from reins import policy as pol  # noqa: E402
from reins.cli import DEFAULT_CONFIG  # noqa: E402
from reins.errors import PipelineError  # noqa: E402

GOLDENS = os.path.join(ROOT, "scripts", "goldens")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
HAPPY = os.path.join(FIXTURES, "happy", "001-request-id-header")
EXPRESS = os.path.join(FIXTURES, "express", "001-retry-debug-log")

_failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        _failures.append(name)


def twice(fn):
    """Determinism double-run: byte-compare two independent computations."""
    a, b = fn(), fn()
    return a == b, a


def golden(name, produced, regen):
    path = os.path.join(GOLDENS, name)
    if regen:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(produced)
        print("froze " + name)
        return True
    with open(path, encoding="utf-8") as fh:
        return fh.read() == produced


def merged_copy(src):
    """A temp copy of the happy fixture advanced to DONE by a merged
    decision, so telemetry extraction has an outcome (fixed ts: the
    projection must not read the wall clock)."""
    tmp = tempfile.mkdtemp(prefix="selftest-")
    task = os.path.join(tmp, os.path.basename(src))
    shutil.copytree(src, task)
    d = decisions.make("merged", "2026-07-25T10:00:00Z", commit="f00dfeed")
    decisions.append(task, d)
    return tmp, task


def main():
    regen = "--regen" in sys.argv[1:]

    # 1. entry point runs from a foreign cwd with no PYTHONPATH
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "reins_cli.py"), "--help"],
        cwd=tempfile.gettempdir(), env=env, capture_output=True, text=True)
    check("entry-point smoke (foreign cwd, no PYTHONPATH)",
          proc.returncode == 0 and "task" in proc.stdout, proc.stderr)

    # 2. hash determinism against an embedded constant
    check("sha256 golden", artifact.sha256_bytes(b"reins\n") ==
          "sha256:8dd411ef756e4cd0a774da3d7af010150f4966f092e0ff21ffd5285e5758eed1")

    # 3. fixture chain integrity from first principles
    for lane, task_dir in (("happy", HAPPY), ("express", EXPRESS)):
        ok, detail = True, ""
        for fname in sorted(os.listdir(task_dir)):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(task_dir, fname)
            a = artifact.load(path)
            r = artifact.loads(artifact.dumps(a), a.path)
            if (r.frontmatter, r.preamble, r.sections) != (
                    a.frontmatter, a.preamble, a.sections):
                ok, detail = False, fname + " round-trip"
                break
            if artifact.body_text(r) != artifact.body_text(a):
                ok, detail = False, fname + " body bytes"
                break
            for name, ref in artifact.consumed_hashes(a).items():
                if ref.startswith("git:"):
                    continue  # a git object reference, not a content hash (D16)
                upstream = os.path.join(task_dir, name + ".md")
                if artifact.sha256(upstream) != ref:
                    ok, detail = False, f"{fname} pin {name}"
        check(f"fixture chain integrity ({lane})", ok, detail)

    # 4. validator: fixtures valid, malformed corpus rejected with types
    report = validate.validate_task(HAPPY)
    check("validator accepts the happy fixture",
          all(a.status == "fresh" for a in report.artifacts.values())
          and not report.task_violations)
    malformed = os.path.join(FIXTURES, "malformed")
    ok = True
    for fname in sorted(os.listdir(malformed)):
        try:
            artifact.load(os.path.join(malformed, fname))
            ok = False
        except PipelineError:
            pass
    check("malformed corpus raises typed errors", ok)

    # 5. frontier derivation vs frozen goldens, computed twice
    for lane, task_dir in (("happy", HAPPY), ("express", EXPRESS)):
        stable, out = twice(lambda d=task_dir: frontier.frontier(d).to_json())
        check(f"frontier determinism ({lane})", stable)
        check(f"frontier golden ({lane})",
              golden(f"frontier_{lane}.json", out + "\n", regen))

    # 6. floor policy vectors against the shipped default config
    policy = pol.resolve(miniyaml.loads(DEFAULT_CONFIG))
    vectors = [
        (["src/auth/token.py"], 5, "full"),      # governed path
        (["src/api/retry.py"], 5, "express"),    # small ordinary change
        (["a.py", "b.py", "c.py", "d.py"], 5, "full"),   # over max_files
        (["src/api/retry.py"], 500, "full"),     # over max_lines
        (["src/api/retry.py"], None, "full"),    # unmeasured fails safe
        ([], 1, "full"),                         # no facts fails safe
    ]
    ok, detail = True, ""
    for paths, lines, expect in vectors:
        got = floor.compute(
            {"changed_paths": paths, "lines_changed": lines}, policy)["floor"]
        if got != expect:
            ok, detail = False, f"{paths}/{lines}: {got} != {expect}"
            break
    check("floor policy vectors", ok, detail)
    stable, _ = twice(lambda: json.dumps(
        floor.compute({"changed_paths": ["src/auth/x.py"], "lines_changed": 3},
                      policy), sort_keys=True))
    check("floor determinism", stable)

    # 7. telemetry extraction golden + idempotent append (no wall clock)
    tmp, task = merged_copy(HAPPY)
    try:
        stable, record = twice(lambda: json.dumps(
            telemetry.extract(task), indent=2, sort_keys=True))
        check("telemetry determinism", stable)
        check("telemetry golden",
              golden("telemetry_happy.json", record + "\n", regen))
        log = os.path.join(tmp, "telemetry.jsonl")
        telemetry.append(json.loads(record), log)
        telemetry.append(json.loads(record), log)
        with open(log, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        check("telemetry append idempotency", n == 1)
    finally:
        shutil.rmtree(tmp)

    # 8. miniyaml vectors (the constructs the pipeline actually uses)
    check("miniyaml vectors", all([
        miniyaml.loads("consumes: [request]") == {"consumes": ["request"]},
        miniyaml.loads("bypass: false  # retired") == {"bypass": False},
        miniyaml.loads("produced_at: 2026-07-25T09:55:00Z")
        == {"produced_at": "2026-07-25T09:55:00Z"},
        miniyaml.loads("consumes:\n- artifact: a\n  hash: b")
        == {"consumes": [{"artifact": "a", "hash": "b"}]},
        miniyaml.loads(miniyaml.dumps({"a": 1, "b": [], "c": "x: y"}))
        == {"a": 1, "b": [], "c": "x: y"},
    ]))
    try:
        miniyaml.loads("m: {a: 1}")
        check("miniyaml rejects the unsupported loudly", False)
    except miniyaml.MiniYamlError:
        check("miniyaml rejects the unsupported loudly", True)

    print()
    if _failures:
        print(f"SELFTEST FAILED: {len(_failures)} check(s): "
              + ", ".join(_failures))
        return 1
    print("selftest passed: the core derives deterministically on "
          + f"Python {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
