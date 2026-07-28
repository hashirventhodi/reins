"""Floor computation (M6/D18): the minimum process a change deserves.

A pure function of (facts, config). The *runtime* owns git and repository
inspection and supplies the facts; this module never reads a repository,
never shells out, and never consults a clock. That is what makes a floor
reproducible: the same facts and the same policy always yield the same
floor, so any historical task can be re-judged under today's policy.

The floor exists to stop an agent lowering its own oversight, so it is
**fail-safe in one direction only: anything unknown raises the floor.** No
policy configured, an unmeasured diff extent, a pattern that matches
nothing it should — every uncertainty resolves to `full`, never `express`.
A floor that fails toward less process would be worse than no floor, since
it would look like a control while granting the cheap lane by accident.

What the floor is NOT: it does not choose a lane. It states the minimum. A
human may dispose at or above it (and, with a recorded reason, below it);
that is the disposition's job, not this module's.
"""

from __future__ import annotations

import re

from .schemas import LANES

# Conservative defaults, used when a floor policy exists but omits a limit.
# Small on purpose: the failure mode of a too-small limit is more process.
DEFAULT_MAX_FILES = 3
DEFAULT_MAX_LINES = 100

EXPRESS, FULL = LANES[0], LANES[-1]


def _glob_to_regex(pattern: str) -> str:
    """Translate a path glob to a regex, segment by segment.

    Deliberately predictable rather than clever, because these patterns are
    security-relevant and read by humans:

      ``*``   matches within one path segment (never crosses ``/``)
      ``?``   matches one character within a segment
      ``**``  matches zero or more whole segments

    So ``auth/**`` covers everything under auth/, ``*.py`` covers top-level
    Python files only, and ``a/**/b`` matches ``a/b`` as well as ``a/x/b``.
    fnmatch is not used: there ``*`` crosses separators, which would make
    ``*.md`` silently match every markdown file in the tree and force every
    task to `full`.
    """
    segments = pattern.split("/")
    out = ["^"]
    for i, segment in enumerate(segments):
        last = i == len(segments) - 1
        if segment == "**":
            out.append(".*" if last else "(?:[^/]+/)*")
        else:
            out.append("".join(
                "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch)
                for ch in segment))
            if not last:
                out.append("/")
    out.append("$")
    return "".join(out)


def matches(path: str, pattern: str) -> bool:
    """Whether one changed path is covered by one governed pattern."""
    return re.match(_glob_to_regex(pattern), path) is not None


def compute(facts: dict, config: dict | None) -> dict:
    """The minimum lane for a change, with the basis for that judgment.

    facts (runtime-supplied):
      changed_paths  list[str] — repo-relative, forward slashes
      lines_changed  int | None — total added+removed; None means unmeasured

    config: the `floor:` mapping from .dev/config.yaml, or None if absent.
      governed_paths  list[str] — globs that force `full`
      max_files       int
      max_lines       int

    Returns a JSON-serializable, deterministic dict: the floor, the basis it
    was computed from, and human-readable reasons — the floor has to be
    explainable, or nobody will trust it when it says `full`.
    """
    changed = sorted(str(p) for p in (facts.get("changed_paths") or []))
    lines = facts.get("lines_changed")
    if lines is not None:
        lines = int(lines)

    governed = list((config or {}).get("governed_paths") or [])
    max_files = int((config or {}).get("max_files", DEFAULT_MAX_FILES))
    max_lines = int((config or {}).get("max_lines", DEFAULT_MAX_LINES))

    matched = [{"path": path, "pattern": pattern}
               for path in changed for pattern in governed
               if matches(path, pattern)]

    reasons: list[str] = []
    if config is None:
        reasons.append("no floor policy configured: .dev/config.yaml has no "
                       "'floor:' block, so no change can be judged small")
    if not changed:
        reasons.append("no changed paths supplied: extent unknown")
    for m in matched:
        reasons.append(f"governed path {m['path']} matches {m['pattern']}")
    if len(changed) > max_files:
        reasons.append(f"{len(changed)} files changed, limit {max_files}")
    if changed and lines is None:
        reasons.append("diff extent not measured: lines_changed absent")
    elif lines is not None and lines > max_lines:
        reasons.append(f"{lines} lines changed, limit {max_lines}")

    return {
        "floor": FULL if reasons else EXPRESS,
        "basis": {
            "configured": config is not None,
            "files": len(changed),
            "lines_changed": lines,
            "governed_matches": matched,
            "limits": {"max_files": max_files, "max_lines": max_lines},
        },
        "reasons": reasons,
    }


def at_or_above(lane: str, floor: str) -> bool:
    """Whether `lane` carries at least as much process as `floor`.

    The ordering check Phase 3b enforces on a disposition. Unknown names are
    rejected rather than ordered — an unrecognised lane must never satisfy a
    floor by accident.
    """
    if lane not in LANES or floor not in LANES:
        return False
    return LANES.index(lane) >= LANES.index(floor)
