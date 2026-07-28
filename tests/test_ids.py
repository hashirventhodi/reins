"""Task identity (D38): allocation, slugs, parsing, reference matching.

The module is pure, so these are unit tests with no filesystem. What is
worth pinning is not that the functions run but that their *failure
directions* hold: never reuse a number, never guess between candidates.
"""

from __future__ import annotations

import pytest

from reins import ids


# --- slugs ------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Add a request id header", "add-a-request-id-header"),
    ("  Mixed CASE and   spaces  ", "mixed-case-and-spaces"),
    ("Punctuation: it's here!", "punctuation-it-s-here"),
    ("2FA support", "2fa-support"),
    ("---", "task"),
    ("", "task"),
    ("....", "task"),
])
def test_slugify_is_deterministic_and_safe(title, expected):
    assert ids.slugify(title) == expected
    assert ids.slugify(title) == ids.slugify(title)


def test_slugify_truncates_at_a_word_boundary():
    slug = ids.slugify("add a request id header to every single api "
                       "response across the whole service")
    assert len(slug) <= ids.MAX_SLUG_LENGTH
    assert not slug.endswith("-")
    assert slug.split("-")[-1] in {"api", "every", "single", "to", "response"}
    # a boundary-less title still respects the cap
    assert len(ids.slugify("a" * 100)) <= ids.MAX_SLUG_LENGTH


# --- parsing ----------------------------------------------------------

def test_parse_round_trips_what_format_produces():
    for number, slug, key in [(1, "first", None), (7, "add-header", None),
                              (42, "x", "API"), (1000, "big", None)]:
        raw = ids.format_id(number, slug, key)
        tid = ids.parse(raw)
        assert tid is not None and tid.raw == raw
        assert (tid.number, tid.slug, tid.key) == (number, slug, key)


def test_format_pads_to_three_but_does_not_cap():
    assert ids.format_id(7, "x") == "007-x"
    assert ids.format_id(42, "x") == "042-x"
    assert ids.format_id(1234, "x") == "1234-x"       # grows, never truncated
    assert ids.format_id(7, "x", key="API") == "API-007-x"


def test_format_rejects_nonsense_rather_than_emitting_it():
    with pytest.raises(ValueError):
        ids.format_id(0, "x")                          # numbering starts at 1
    with pytest.raises(ValueError):
        ids.format_id(1, "x", key="9bad")              # keys start with a letter


@pytest.mark.parametrize("name", [
    "", "no-number", "007", "-007-x", "007-", "007-UPPER", "x/y",
])
def test_parse_returns_none_for_non_ids(name):
    """None is a normal answer: a directory that is not a task id is
    skipped, never a crash."""
    assert ids.parse(name) is None


# --- allocation -------------------------------------------------------

def test_allocation_is_sequential_from_one():
    existing: list[str] = []
    for expected in ("001-first", "002-second", "003-third"):
        new = ids.allocate(expected.split("-", 1)[1].replace("-", " "), existing)
        assert new == expected
        existing.append(new)


def test_allocation_never_reuses_a_number_after_deletion():
    """The one rule allocation cannot break: ids are hashed into artifact
    pins, so a reused number would collide with evidence that still
    exists elsewhere (telemetry, a followup ref, a merged branch)."""
    existing = ["001-a", "002-b", "003-c"]
    del existing[1]                                    # 002 deleted
    assert ids.allocate("next", existing) == "004-next"


def test_allocation_ignores_unparseable_neighbours():
    assert ids.allocate("x", ["notes", "README.md", "005-real"]) == "006-x"


def test_numbering_is_per_key_so_adopting_one_starts_a_series():
    existing = ["001-a", "002-b"]
    assert ids.allocate("x", existing, key="API") == "API-001-x"
    assert ids.allocate("y", existing + ["API-001-x"], key="API") == "API-002-y"
    assert ids.allocate("z", existing + ["API-001-x"]) == "003-z"


def test_allocation_is_not_confused_by_gaps_or_order():
    assert ids.allocate("x", ["010-j", "002-b", "007-g"]) == "011-x"


# --- concurrent-branch collisions (the Rails problem) -----------------

def test_duplicate_numbers_are_detected_not_hidden():
    """Two branches allocating concurrently both get 007. Reins tolerates
    that — ids are identity, not an execution order — but it must be
    visible rather than silent."""
    names = ["007-alice-work", "007-bob-work", "008-solo"]
    assert ids.duplicate_numbers(names) == {7: ["007-alice-work",
                                                "007-bob-work"]}
    assert ids.duplicate_numbers(["001-a", "002-b"]) == {}


def test_duplicate_detection_is_per_key():
    assert ids.duplicate_numbers(["001-a", "API-001-b"]) == {}


# --- reference matching ----------------------------------------------

ENTRIES = [
    ("007-add-a-request-id-header", "Add a request id header"),
    ("008-retry-the-upload-path", "Retry the upload path"),
    ("009-retry-the-download-path", "Retry the download path"),
]


@pytest.mark.parametrize("ref,expected", [
    ("007-add-a-request-id-header", "007-add-a-request-id-header"),  # exact
    ("7", "007-add-a-request-id-header"),        # bare number, no padding
    ("007", "007-add-a-request-id-header"),      # padded number
    ("request-id", "007-add-a-request-id-header"),   # id fragment
    ("Add a request", "007-add-a-request-id-header"),  # title fragment
    ("UPLOAD", "008-retry-the-upload-path"),     # case-insensitive
])
def test_single_match_resolves(ref, expected):
    assert ids.match(ref, ENTRIES) == [expected]


def test_ambiguous_reference_returns_every_candidate():
    """It never picks a winner: a typo that acted on the wrong task would
    cost far more than the keystrokes saved."""
    assert ids.match("retry", ENTRIES) == ["008-retry-the-upload-path",
                                           "009-retry-the-download-path"]


def test_exact_id_wins_even_when_it_is_a_substring_of_another():
    entries = [("001-api", "API"), ("002-api-gateway", "API gateway")]
    assert ids.match("001-api", entries) == ["001-api"]
    assert ids.match("api", entries) == ["001-api", "002-api-gateway"]


def test_number_match_beats_incidental_substrings():
    """`7` means task 7, not 'every id containing a 7'."""
    entries = [("007-alpha", "Alpha"), ("017-beta", "Beta"),
               ("027-gamma", "Gamma")]
    assert ids.match("7", entries) == ["007-alpha"]


def test_unknown_and_empty_references_match_nothing():
    for ref in ("", "   ", "nonexistent", "999"):
        assert ids.match(ref, ENTRIES) == []


def test_matching_tolerates_missing_titles():
    entries = [("007-x", ""), ("008-y", None)]
    assert ids.match("8", entries) == ["008-y"]
    assert ids.match("x", entries) == ["007-x"]
