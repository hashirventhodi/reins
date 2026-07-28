"""Task identity: allocation, slugs, parsing, and reference matching.

Convention (D38): ``<NNN>-<slug>`` — ``007-add-a-request-id-header`` —
optionally carrying a project key, ``API-007-add-a-request-id-header``.
This is the shape Architecture Decision Records (``0001-use-postgres.md``),
Django migrations (``0001_initial.py``) and GitHub's Spec Kit
(``specs/001-feature-name/``) all converged on, for the same reason: the
number is a handle short enough to type, the slug keeps the directory
listing readable, and neither has to win.

Two properties are load-bearing and deliberately chosen:

**Ids are immutable.** A task id is written into every downstream
artifact's frontmatter and is hashed into the pins that make the chain
verifiable. Renumbering a task would invalidate its own evidence, so
there is no renumber operation and never will be — which is precisely
why allocation must never *reuse* a number.

**Numbers are derived, never stored.** The next number is a function of
the directory, exactly as ADR tooling and Django do it. A counter file
would be a merge conflict on every branch and a lie whenever someone
edited it.

The known cost is the one Rails hit and solved by moving migrations to
timestamps: two branches allocating concurrently both get ``007``. Reins
tolerates that rather than trading it for unreadable timestamp ids,
because the failure is *benign here* — task ids are identity, not an
execution order, so a duplicate number is a naming clash and never a
corrupt run. It is handled in the only two places it can surface:
:func:`match` refuses an ambiguous reference instead of guessing, and
:func:`duplicate_numbers` lets the CLI show the clash so a human can see
it. Refusing beats guessing; both beat a timestamp nobody can type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "TaskId", "DEFAULT_WIDTH", "MAX_SLUG_LENGTH", "KEY_RE",
    "slugify", "parse", "format_id", "next_number", "allocate",
    "duplicate_numbers", "match",
]

DEFAULT_WIDTH = 3          # 007; wider numbers simply grow, they are not capped
MAX_SLUG_LENGTH = 48       # long enough to stay descriptive, short enough to type

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

_ID_RE = re.compile(
    r"^(?:(?P<key>[A-Za-z][A-Za-z0-9]*)-)?"
    r"(?P<number>\d+)-"
    r"(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"^\d+$")


@dataclass(frozen=True)
class TaskId:
    """A parsed task id. ``raw`` is always the authoritative string."""

    raw: str
    number: int
    slug: str
    key: str | None = None


def slugify(title: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """A deterministic, filesystem-safe slug for a title.

    Truncation is at a word boundary so the slug stays readable rather
    than ending mid-word. Deliberately no stop-word removal: dropping
    "the" and "a" makes slugs marginally shorter and materially harder
    to predict, and a human guessing at their own task's slug is the
    whole point of having one.
    """
    slug = _NON_SLUG.sub("-", title.lower()).strip("-")
    if not slug:
        return "task"
    if len(slug) <= max_length:
        return slug
    cut = slug[:max_length + 1]
    boundary = cut.rfind("-")
    trimmed = (cut[:boundary] if boundary > 0 else slug[:max_length])
    return trimmed.strip("-") or slug[:max_length].strip("-") or "task"


def parse(name: str) -> TaskId | None:
    """Parse a task id, or None if `name` is not one.

    None is a normal answer, not an error: a task directory may predate
    this convention, and callers skip what they cannot parse rather than
    failing on it.
    """
    m = _ID_RE.match(name or "")
    if not m:
        return None
    return TaskId(raw=name, number=int(m.group("number")),
                  slug=m.group("slug"), key=m.group("key"))


def format_id(number: int, slug: str, key: str | None = None,
              width: int = DEFAULT_WIDTH) -> str:
    """Render an id. Padding is cosmetic — numbers past the width grow."""
    if number < 1:
        raise ValueError(f"task numbers start at 1, got {number}")
    if key is not None and not KEY_RE.match(key):
        raise ValueError(f"invalid task key {key!r}: letters and digits, "
                         "starting with a letter")
    body = f"{number:0{width}d}-{slug}"
    return f"{key}-{body}" if key else body


def next_number(existing: Iterable[str], key: str | None = None) -> int:
    """One past the highest number in `existing`, counting from 1.

    Numbering is per key, so adopting a key starts a fresh series
    instead of renumbering anything. Unparseable names are ignored —
    they cannot be reasoned about, and refusing to allocate because of
    one would be worse than skipping it.
    """
    highest = 0
    for name in existing:
        tid = parse(name)
        if tid is not None and tid.key == key:
            highest = max(highest, tid.number)
    return highest + 1


def allocate(title: str, existing: Iterable[str], key: str | None = None,
             width: int = DEFAULT_WIDTH) -> str:
    """The id a new task with `title` should receive."""
    names = list(existing)
    return format_id(next_number(names, key), slugify(title), key, width)


def duplicate_numbers(names: Iterable[str],
                      key: str | None = None) -> dict[int, list[str]]:
    """Numbers claimed by more than one task, e.g. after merging two
    branches that each allocated concurrently (the Rails collision).

    Returns ``{number: [ids...]}``, each list sorted, empty when clean.
    """
    by_number: dict[int, list[str]] = {}
    for name in names:
        tid = parse(name)
        if tid is not None and tid.key == key:
            by_number.setdefault(tid.number, []).append(name)
    return {n: sorted(v) for n, v in sorted(by_number.items()) if len(v) > 1}


def match(ref: str, entries: Sequence[tuple[str, str]]) -> list[str]:
    """Task ids matching a human's reference, most precise rule first.

    `entries` is (task_id, title) pairs. The rules, in order:

    1. an exact id — always wins outright, so a full id is never ambiguous;
    2. a bare number — ``7`` finds ``007`` without the padding, which is
       what someone reading `task list` will type;
    3. a case-insensitive fragment of the id or of the title, so
       ``request-id`` finds it too.

    Returns every match, sorted. One is a hit, several are ambiguous, and
    none is unknown — the caller decides how to say so. This function
    never picks a winner among several: choosing "best" would let a typo
    act on the wrong task, and no keystroke saving is worth that.
    """
    ref = (ref or "").strip()
    if not ref:
        return []
    ids = [tid for tid, _ in entries]
    if ref in ids:
        return [ref]
    if _DIGITS.match(ref):
        wanted = int(ref)
        hits = [tid for tid in ids
                if (p := parse(tid)) is not None and p.number == wanted]
        if hits:
            return sorted(hits)
    needle = ref.lower()
    return sorted(tid for tid, title in entries
                  if needle in tid.lower() or needle in (title or "").lower())
