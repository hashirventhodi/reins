"""The deterministic CLI (M2 core) — a thin wrapper over the modules.

Exit codes (blueprint §2.8):
  0 ok · 1 usage/user error · 2 validation failure · 3 blocked/awaiting-human

Every subcommand is safe to re-run. --json gives machine-readable output.
The CLI is usable standalone: a human with no AI can run the entire state
machine (this is the model-agnosticism property as a tool).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from . import artifact as art
from . import ids
from . import miniyaml
from . import decisions as dec
from . import frontier as fr
from . import validate as val
from .errors import ArtifactParseError, PipelineError
from .schemas import (
    CHAIN,
    LANES,
    PIPELINE_VERSION,
    REF_PREFIXES,
    SCHEMAS,
    VERIFICATION_VERDICTS,
)

TASKS_DIR = Path(".dev") / "tasks"

OK, USAGE, INVALID_STATE, NEEDS_HUMAN = 0, 1, 2, 3

# Starter project config. The floor policy is deliberately present but
# minimal: an absent 'floor:' block means every change is judged `full`
# (D18), so a fresh repo is safe rather than accidentally cheap. The paths
# below are the surfaces where a small diff is most often not a small risk;
# every repo is expected to edit this list. `.dev/config.yaml` governs
# itself — changing the bar is never express work.
#
# Patterns are depth-independent on purpose (D25). A root-anchored `auth/**`
# governs nothing in a repo that keeps code under src/, lib/, app/ or pkg/,
# and a policy that silently matches nothing is worse than none: it looks
# like a control while granting the cheap lane to a session-token change.
# `.github/**` and `.dev/config.yaml` stay root-anchored because that is
# where they are actually required to live.
DEFAULT_CONFIG = f"""# reins project config
pipeline: {PIPELINE_VERSION}
telemetry: telemetry.jsonl

# Task id prefix (D38). Ids are `<NNN>-<slug>`: 001-add-a-request-id-header.
# Set a project key for Jira-shaped ids — `task_key: API` gives API-001-...
# Numbering is per key, so adopting one starts its own series; existing
# tasks keep the ids they were given, because ids are hashed into the
# artifact chain and can never be renumbered.
# task_key: API

# Minimum-process policy (D18). Facts come from the runtime; this is policy.
# Patterns match at any depth: '**/auth/**' covers auth/ and src/auth/ alike.
floor:
  governed_paths:
    - .dev/config.yaml
    - .github/**
    - '**/auth/**'
    - '**/crypto/**'
    - '**/migrations/**'
    - '**/infra/**'
    - '**/secrets/**'
    - '**/Dockerfile'
    - '**/package.json'
    - '**/pyproject.toml'
    - '**/requirements*.txt'
    - '**/go.mod'
    - '**/Cargo.toml'
  max_files: 3
  max_lines: 100
"""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task_key(root: Path):
    """The optional project key from `.dev/config.yaml` (`task_key:`).

    None by default, giving `007-add-a-request-id-header` — the ADR and
    Spec Kit shape. Setting `task_key: API` gives Jira-shaped ids,
    `API-007-...`, and starts that key's own series (D38)."""
    cfg = root / ".dev" / "config.yaml"
    if not cfg.exists():
        return None
    try:
        data = miniyaml.loads(cfg.read_text(encoding="utf-8")) or {}
    except miniyaml.MiniYamlError:
        return None
    key = data.get("task_key") if isinstance(data, dict) else None
    if isinstance(key, str) and key and ids.KEY_RE.match(key):
        return key
    return None


def _task_names(root: Path):
    base = root / TASKS_DIR
    return sorted(p.name for p in base.iterdir() if p.is_dir()) \
        if base.is_dir() else []


def _request_body(path: Path) -> bytes | None:
    """The verbatim body of a request.md, frontmatter stripped."""
    raw = path.read_bytes()
    if not raw.startswith(b"---\n"):
        return None
    end = raw.find(b"\n---\n", 3)
    return None if end == -1 else raw[end + 5:]


def _duplicate_request(root: Path, source_ref: str, body: bytes):
    """An existing task with the same source and byte-identical body.

    Descriptive ids used to make this free: the same title on the same
    day collided, which backstopped duplicate follow-up creation. Numeric
    ids never collide, so the guarantee is restored here — on content,
    which catches duplicates the title-based check would have missed."""
    base = root / TASKS_DIR
    if not base.is_dir():
        return None
    for p in sorted(base.iterdir()):
        req = p / "request.md"
        if not (p.is_dir() and req.is_file()):
            continue
        try:
            a = art.load(req)
        except PipelineError:
            continue
        if a.frontmatter.get("source_ref") != source_ref:
            continue
        if _request_body(req) == body:
            return p.name
    return None


def _task_title(task_dir: Path) -> str:
    """The captured title, or '' for requests written before D38."""
    req = task_dir / "request.md"
    if not req.is_file():
        return ""
    try:
        title = art.load(req).frontmatter.get("title")
    except PipelineError:
        return ""
    return title if isinstance(title, str) else ""


def _resolve_task(root: Path, ref: str) -> str:
    """Resolve a human's task reference to exactly one id (D37, D38).

    The matching policy lives in `ids.match`; this adds the filesystem
    and the error messages. Ambiguity names every candidate with its
    title, because with short ids the title is how a human tells them
    apart."""
    base = root / TASKS_DIR
    if not (ref or "").strip():
        raise PipelineError("empty task reference")
    if (base / ref).is_dir():
        return ref
    if not base.is_dir():
        raise PipelineError(f"no tasks directory: {base} (run init first)")
    entries = [(name, _task_title(base / name)) for name in _task_names(root)]
    hits = ids.match(ref, entries)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise PipelineError(f"no such task: {ref} (looked in {base})")
    titles = dict(entries)
    listing = "\n  ".join(f"{h:<28} {titles.get(h, '')}".rstrip() for h in hits)
    raise PipelineError(
        f"ambiguous task reference {ref!r} — {len(hits)} tasks match:\n"
        f"  {listing}\nuse a longer fragment or the full id")


def _task_dir(root: Path, task_id: str) -> Path:
    d = root / TASKS_DIR / _resolve_task(root, task_id)
    if not d.is_dir():
        raise PipelineError(f"no such task: {task_id} (looked in {d})")
    return d


# --- subcommands -----------------------------------------------------------

def cmd_init(args) -> int:
    root = Path(args.root)
    (root / TASKS_DIR).mkdir(parents=True, exist_ok=True)
    cfg = root / ".dev" / "config.yaml"
    if not cfg.exists():
        cfg.write_text(DEFAULT_CONFIG, encoding="utf-8")
    tele = root / "telemetry.jsonl"
    if not tele.exists():
        tele.touch()
    print(f"initialized {root / '.dev'}")
    return OK


def cmd_task_add(args) -> int:
    root = Path(args.root)
    if args.body is not None and args.body_file is not None:
        print("use --body or --body-file, not both", file=sys.stderr)
        return USAGE
    if args.body is not None:
        body = args.body.encode("utf-8")
    elif args.body_file is not None:
        body = Path(args.body_file).read_bytes()   # byte-exact (M5-A: verbatim)
    else:
        body = sys.stdin.buffer.read()
    dup = _duplicate_request(root, args.source_ref, body)
    if dup is not None:
        print(f"duplicate request: an identical body from source-ref "
              f"{args.source_ref!r} is already captured as {dup}; "
              "nothing added", file=sys.stderr)
        return USAGE
    task_id = ids.allocate(args.title, _task_names(root),
                           key=_task_key(root))
    d = root / TASKS_DIR / task_id
    if d.exists():
        print(f"task id collision: {task_id} already exists", file=sys.stderr)
        return USAGE
    d.mkdir(parents=True)
    # miniyaml quotes whatever needs it, so a title with a colon is safe
    fm = ("---\n" + miniyaml.dumps({
        "task": task_id, "title": args.title,
        "source_ref": args.source_ref, "created_at": _now(),
    }) + "---\n").encode("utf-8")
    (d / "request.md").write_bytes(fm + body)
    print(task_id)
    return OK


def cmd_task_list(args) -> int:
    root = Path(args.root)
    base = root / TASKS_DIR
    rows = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        f = fr.frontier(d)
        rows.append({"task": f.task, "title": _task_title(d),
                     "status": f.status, "next_contract": f.next_contract})
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return OK
    # Ids vary in width, so the columns are measured, not guessed.
    dupes = ids.duplicate_numbers([r["task"] for r in rows], _task_key(root))
    clashing = {t for names in dupes.values() for t in names}
    width = max((len(r["task"]) for r in rows), default=0)
    for r in rows:
        mark = " !" if r["task"] in clashing else "  "
        print(f"{r['task']:<{width}}{mark} {r['status']:<24} "
              f"next={r['next_contract'] or '-':<10} {r['title']}".rstrip())
    if dupes:
        # Two branches allocated the same number and were merged. Benign
        # for the chain — ids stay unique — but a human should see it,
        # and short references to that number are now ambiguous.
        for number, names in dupes.items():
            print(f"! number {number} is claimed by {len(names)} tasks: "
                  f"{', '.join(names)}", file=sys.stderr)
    return OK


def cmd_task_show(args) -> int:
    d = _task_dir(Path(args.root), args.task)
    f = fr.frontier(d)
    present = [a for a in CHAIN if (d / SCHEMAS[a].filename).exists()]
    out = {"frontier": f.to_dict(), "artifacts_present": present,
           "decisions": [x.to_dict() for x in dec.read(d).decisions]}
    print(json.dumps(out, indent=2, sort_keys=True) if args.json else
          miniyaml.dumps(out))
    return OK


def _status_exit(f: fr.Frontier) -> int:
    if f.status == "INVALID":
        return INVALID_STATE
    if f.status in fr.HUMAN_STATUSES:
        return NEEDS_HUMAN
    return OK


def cmd_status(args) -> int:
    f = fr.frontier(_task_dir(Path(args.root), args.task))
    print(f.to_json() if args.json else
          f"{f.task}\n  status: {f.status}\n  next:   "
          f"{f.next_contract or '-'}\n  reason: {f.reason}")
    return _status_exit(f)


def cmd_next(args) -> int:
    f = fr.frontier(_task_dir(Path(args.root), args.task))
    print(f.next_contract or "-")
    return _status_exit(f)


def cmd_validate(args) -> int:
    d = _task_dir(Path(args.root), args.task)
    report = val.validate_task(d)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return OK if report.is_valid else INVALID_STATE


def cmd_consent(args) -> int:
    d = _task_dir(Path(args.root), args.task)
    gate = {"intent": ("intent_confirmed", "intent", "intent_hash"),
            "plan": ("plan_approved", "plan", "plan_hash")}[args.gate]
    dtype, atype, hash_field = gate
    path = d / SCHEMAS[atype].filename
    if not path.exists():
        print(f"{path.name} does not exist; nothing to consent to",
              file=sys.stderr)
        return USAGE
    if val.validate_artifact(path, d.name):
        print(f"{path.name} is invalid; consent refused "
              "(run validate for details)", file=sys.stderr)
        return INVALID_STATE
    dec.append(d, dec.make(dtype, _now(),
                           **{hash_field: art.sha256(path),
                              "edited": bool(args.edited)}))
    print(f"recorded {dtype} pinning current {path.name}")
    return OK


def cmd_decide(args) -> int:
    d = _task_dir(Path(args.root), args.task)
    ts = _now()
    try:
        if args.kind == "escalation":
            decision = dec.make("escalation", ts, trigger_id=args.trigger,
                                from_contract=args.from_contract,
                                detail=args.detail)
        elif args.kind == "returned":
            data = {"to_contract": args.to, "reason": args.reason}
            if args.verdict:
                data["verdict"] = args.verdict
            if args.review_hash:
                data["review_hash"] = args.review_hash
            decision = dec.make("returned", ts, **data)
        elif args.kind == "disposition":
            data = {"lane": args.lane, "floor": args.floor}
            if args.reason:
                data["override_reason"] = args.reason
            decision = dec.make("disposition", ts, **data)
        else:  # merged
            decision = dec.make("merged", ts, commit=args.commit)
    except dec.DecisionError as exc:
        print(str(exc), file=sys.stderr)
        return USAGE
    dec.append(d, decision)
    print(f"recorded {decision.type}")
    return OK


def _floor_config(root: Path) -> dict | None:
    """The `floor:` block from .dev/config.yaml, or None if absent.

    None is meaningful, not an error: an unconfigured repo cannot judge any
    change small, so the floor is `full` (D18)."""
    cfg = root / ".dev" / "config.yaml"
    if not cfg.exists():
        return None
    try:
        data = miniyaml.loads(cfg.read_text(encoding="utf-8")) or {}
    except miniyaml.MiniYamlError as exc:
        raise PipelineError(f"{cfg}: invalid YAML ({exc})") from exc
    block = data.get("floor")
    return block if isinstance(block, dict) else None


def cmd_floor(args) -> int:
    """Compute the minimum process a change deserves (D18).

    Facts are supplied, never gathered: git and repository inspection belong
    to the runtime (D12). Reading paths from stdin makes the common case
    `git diff --name-only | pipeline floor <id>`."""
    from . import floor as fl
    d = _task_dir(Path(args.root), args.task)
    if args.changed_paths_file:
        raw = Path(args.changed_paths_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    facts = {
        "changed_paths": [ln.strip() for ln in raw.splitlines() if ln.strip()],
        "lines_changed": args.lines_changed,
    }
    result = fl.compute(facts, _floor_config(Path(args.root)))
    result["task"] = d.name
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{d.name}\n  floor: {result['floor']}")
        for reason in result["reasons"]:
            print(f"    - {reason}")
        if not result["reasons"]:
            print(f"    - {result['basis']['files']} file(s), "
                  f"{result['basis']['lines_changed']} line(s), "
                  "no governed paths")
    return OK


def cmd_floor_check(args) -> int:
    """Compare the *realized* floor against the lane actually disposed (D20).

    The predictive floor is computed before work from intended paths; this
    is the same function over what the diff turned out to be. A task that
    was disposed `express` and then touched a governed surface is a lane
    violation — caught mechanically at the gate rather than by a human
    noticing. Absent disposition means `full`, which no floor can exceed."""
    from . import floor as fl
    d = _task_dir(Path(args.root), args.task)
    if args.changed_paths_file:
        raw = Path(args.changed_paths_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    realized = fl.compute(
        {"changed_paths": [ln.strip() for ln in raw.splitlines() if ln.strip()],
         "lines_changed": args.lines_changed},
        _floor_config(Path(args.root)))

    latest = dec.read(d).latest("disposition")
    lane = latest.data["lane"] if latest else fl.FULL
    # A recorded override is the human's decision to run below the floor —
    # it has to actually clear the gate, or the escape hatch is decorative
    # and people route around the system instead. It covers a realized floor
    # no higher than the one it was recorded against, and it is reported,
    # never silently green.
    override_reason = (latest.data.get("override_reason") if latest else None)
    covered = bool(override_reason) and fl.at_or_above(latest.data["floor"],
                                                       realized["floor"])
    ok = fl.at_or_above(lane, realized["floor"]) or covered
    result = {"task": d.name, "lane": lane, "realized_floor": realized["floor"],
              "ok": ok, "disposed": latest is not None,
              "override_reason": override_reason if covered else None,
              "reasons": realized["reasons"]}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif covered:
        print(f"{d.name}\n  lane {lane} is BELOW realized floor "
              f"{realized['floor']}, allowed by a recorded override:\n"
              f"    {override_reason}")
    elif ok:
        print(f"{d.name}\n  lane {lane} satisfies realized floor "
              f"{realized['floor']}")
    else:
        print(f"LANE VIOLATION: {d.name} ran as {lane}, but the realized "
              f"floor is {realized['floor']}", file=sys.stderr)
        for reason in realized["reasons"]:
            print(f"  - {reason}", file=sys.stderr)
        print("  resolve: run the obligations the higher lane requires, or "
              "record an override:\n"
              f"    pipeline decide disposition {d.name} --lane {lane} "
              f"--floor {realized['floor']} --reason '...'", file=sys.stderr)
    return OK if ok else INVALID_STATE


def cmd_verify(args) -> int:
    """Record a verification result (D17). The product never runs anything:

    the runtime owns tools, clocks, and git, and supplies the judgment it
    reached. Evidence is pinned by hashing the captured output here, so the
    caller never hand-writes a hash (R2)."""
    d = _task_dir(Path(args.root), args.task)
    if (args.evidence_file is None) == (args.evidence_hash is None):
        print("use exactly one of --evidence-file or --evidence-hash",
              file=sys.stderr)
        return USAGE
    evidence = (args.evidence_hash if args.evidence_hash
                else art.sha256(args.evidence_file))
    try:
        decision = dec.make(
            "verification", _now(), verifier=args.verifier, tool=args.tool,
            predicate=args.predicate, verdict=args.verdict,
            tree_ref=args.tree_ref, evidence_hash=evidence,
            standard_touched=bool(args.standard_touched))
    except dec.DecisionError as exc:
        print(str(exc), file=sys.stderr)
        return USAGE
    dec.append(d, decision)
    print(f"recorded verification {args.verifier}={args.verdict} "
          f"against {args.tree_ref}")
    return OK


def cmd_hash(args) -> int:
    print(art.sha256(args.file))
    return OK


def cmd_frontmatter(args) -> int:
    """The only sanctioned way for skills to write frontmatter: models

    must never hand-compute hashes (blueprint R2/§6)."""
    path = Path(args.file)
    # The contracts direct skills to write the body first and set frontmatter
    # only here, but this command could not create the fence it required, so
    # every artifact cost a failed call plus a hand-written fence — in the one
    # command that exists to keep hands off frontmatter (D28). --init closes
    # that loop; without it the old refusal stands, now naming its own fix.
    if getattr(args, "init", False) and path.is_file():
        raw = path.read_text(encoding="utf-8")
        if not raw.lstrip().startswith("---"):
            path.write_text("---\n---\n" + raw, encoding="utf-8")
    try:
        a = art.load(path)
    except ArtifactParseError as exc:
        if "frontmatter fence" in str(exc) and not getattr(args, "init", False):
            print(f"{exc}\n  pass --init to create the fence and keep the body "
                  f"verbatim", file=sys.stderr)
            return USAGE
        raise
    for kv in args.set or []:
        key, _, raw = kv.partition("=")
        if not _:
            print(f"--set expects key=value, got {kv!r}", file=sys.stderr)
            return USAGE
        a.frontmatter[key] = miniyaml.parse_scalar(raw)
    for pin in args.pin or []:
        name, _, target = pin.partition("=")
        if not _:
            print(f"--pin expects artifact=path, got {pin!r}", file=sys.stderr)
            return USAGE
        pins = [e for e in a.frontmatter.get("consumes", [])
                if e.get("artifact") != name]
        # An already-formed reference passes through (a git object id cannot
        # be derived from a path, D16); anything else is a path to hash.
        digest = (target if target.startswith(REF_PREFIXES)
                  else art.sha256(target))
        pins.append({"artifact": name, "hash": digest})
        a.frontmatter["consumes"] = pins
    art.dump(a, path)
    print(f"updated {path}")
    return OK


def cmd_extract(args) -> int:
    from . import telemetry as tele
    d = _task_dir(Path(args.root), args.task)
    try:
        record = tele.extract(d)
    except tele.ExtractionError as exc:
        print(str(exc), file=sys.stderr)
        return INVALID_STATE
    print(json.dumps(record, indent=2, sort_keys=True))
    if args.append:
        path = Path(args.root) / (args.telemetry or tele.DEFAULT_PATH)
        wrote = tele.append(record, path)
        print(f"{'appended to' if wrote else 'already recorded in'} {path}",
              file=sys.stderr)
    return OK


def cmd_followups(args) -> int:
    """Projection only (D14, amended): creation is orchestration and

    belongs to the runtime, which relays the human's selection to
    `pipeline task add` per candidate (see docs/followups.md)."""
    from . import followups as fu
    d = _task_dir(Path(args.root), args.task)
    print(json.dumps(fu.harvest(d), indent=2, sort_keys=True))
    return OK


# --- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline")
    p.add_argument("--root", default=".", help="repo root (default: cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    task = sub.add_parser("task").add_subparsers(dest="task_cmd", required=True)
    t_add = task.add_parser("add")
    t_add.add_argument("--title", required=True)
    t_add.add_argument("--body")
    t_add.add_argument("--body-file")
    t_add.add_argument("--source-ref", default="local")
    t_add.set_defaults(fn=cmd_task_add)
    t_list = task.add_parser("list")
    t_list.add_argument("--json", action="store_true")
    t_list.set_defaults(fn=cmd_task_list)
    t_show = task.add_parser("show")
    t_show.add_argument("task")
    t_show.add_argument("--json", action="store_true")
    t_show.set_defaults(fn=cmd_task_show)

    for name, fn in (("status", cmd_status), ("next", cmd_next),
                     ("validate", cmd_validate)):
        s = sub.add_parser(name)
        s.add_argument("task")
        s.add_argument("--json", action="store_true")
        s.set_defaults(fn=fn)

    c = sub.add_parser("consent")
    c.add_argument("gate", choices=["intent", "plan"])
    c.add_argument("task")
    c.add_argument("--edited", action="store_true",
                   help="the human edited the artifact before consenting "
                        "(the orchestrator sets this by comparing the "
                        "post-generation hash)")
    c.set_defaults(fn=cmd_consent)

    dd = sub.add_parser("decide").add_subparsers(dest="kind", required=True)
    esc = dd.add_parser("escalation")
    esc.add_argument("task")
    esc.add_argument("--trigger", required=True)
    esc.add_argument("--from", dest="from_contract", required=True)
    esc.add_argument("--detail", required=True)
    esc.set_defaults(fn=cmd_decide, kind="escalation")
    ret = dd.add_parser("returned")
    ret.add_argument("task")
    ret.add_argument("--to", required=True)
    ret.add_argument("--reason", required=True)
    ret.add_argument("--verdict")
    ret.add_argument("--review-hash")
    ret.set_defaults(fn=cmd_decide, kind="returned")
    dsp = dd.add_parser("disposition")
    dsp.add_argument("task")
    dsp.add_argument("--lane", required=True, choices=list(LANES))
    dsp.add_argument("--floor", required=True, choices=list(LANES),
                     help="the computed floor this lane was chosen against")
    dsp.add_argument("--reason", help="required only when --lane is below "
                                      "--floor; recorded as override_reason")
    dsp.set_defaults(fn=cmd_decide, kind="disposition")
    # `decide bypass` is retired (D22): the express lane is the cheap path,
    # and it keeps adjudication. The decision type stays readable so historical
    # logs still resolve to BYPASSED; only the way to create one is gone.
    mrg = dd.add_parser("merged")
    mrg.add_argument("task")
    mrg.add_argument("--commit", required=True)
    mrg.set_defaults(fn=cmd_decide, kind="merged")

    fl = sub.add_parser("floor", help="minimum process for a change (D18)")
    fl.add_argument("task")
    fl.add_argument("--changed-paths-file",
                    help="one repo-relative path per line; default: stdin")
    fl.add_argument("--lines-changed", type=int,
                    help="added+removed; omitting it leaves extent "
                         "unmeasured, which raises the floor")
    fl.add_argument("--json", action="store_true")
    fl.set_defaults(fn=cmd_floor)

    fc = sub.add_parser("floor-check",
                        help="realized floor vs the disposed lane (D20)")
    fc.add_argument("task")
    fc.add_argument("--changed-paths-file",
                    help="one repo-relative path per line; default: stdin")
    fc.add_argument("--lines-changed", type=int)
    fc.add_argument("--json", action="store_true")
    fc.set_defaults(fn=cmd_floor_check)

    ver = sub.add_parser("verify", help="record a verification result (D17)")
    ver.add_argument("task")
    ver.add_argument("--verifier", required=True,
                     help="class of check: tests, lint, security, "
                          "performance, migration, … (lowercase slug)")
    ver.add_argument("--tool", required=True,
                     help="what produced the verdict, with version")
    ver.add_argument("--predicate", required=True,
                     help="the claim tested, e.g. 'test suite passes'")
    ver.add_argument("--verdict", required=True,
                     choices=list(VERIFICATION_VERDICTS))
    ver.add_argument("--tree-ref", required=True,
                     help="git:<object id> of the tree verified (D16)")
    ver.add_argument("--evidence-file",
                     help="captured output; the product hashes it")
    ver.add_argument("--evidence-hash", help="a pre-computed sha256: pin")
    ver.add_argument("--standard-touched", action="store_true",
                     help="the diff modified the standard this verifier "
                          "judges by (its tests, rules, or allowlists)")
    ver.set_defaults(fn=cmd_verify)

    h = sub.add_parser("hash")
    h.add_argument("file")
    h.set_defaults(fn=cmd_hash)

    fu = sub.add_parser("followups")
    fu.add_argument("task")
    fu.add_argument("--json", action="store_true")   # output is always JSON
    fu.set_defaults(fn=cmd_followups)

    ex = sub.add_parser("extract")
    ex.add_argument("task")
    ex.add_argument("--append", action="store_true",
                    help="idempotently append to the telemetry log")
    ex.add_argument("--telemetry", help="log path (default: telemetry.jsonl)")
    ex.set_defaults(fn=cmd_extract)

    fm = sub.add_parser("frontmatter")
    fm.add_argument("file")
    fm.add_argument("--set", action="append")
    fm.add_argument("--pin", action="append")
    fm.add_argument("--init", action="store_true",
                    help="create the '---' fence if the file has none")
    fm.set_defaults(fn=cmd_frontmatter)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse uses 2 for usage; our contract says 1
        return OK if exc.code in (0, None) else USAGE
    try:
        return args.fn(args)
    except PipelineError as exc:
        print(str(exc), file=sys.stderr)
        return USAGE


if __name__ == "__main__":
    raise SystemExit(main())
