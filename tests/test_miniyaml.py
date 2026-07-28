"""miniyaml — the restricted YAML subset that replaced PyYAML (D30).

The parser must agree with PyYAML on every document the pipeline actually
reads (modulo the deliberate divergence: timestamps stay strings), the
dumper must reproduce the fixture frontmatter style byte-for-byte, and
anything outside the subset must fail loudly with a typed error.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from reins import miniyaml
from reins.miniyaml import MiniYamlError

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


# --- subset vectors: parsing -----------------------------------------

def test_block_mapping_scalars():
    doc = "pipeline: 1\ncontract: review\nproduced_at: 2026-07-25T09:55:00Z\n"
    assert miniyaml.loads(doc) == {
        "pipeline": 1, "contract": "review",
        "produced_at": "2026-07-25T09:55:00Z",
    }


def test_timestamps_stay_plain_strings():
    """The deliberate divergence from PyYAML: no implicit datetime
    resolution (the D26 bug class)."""
    value = miniyaml.loads("produced_at: 2026-07-25T09:55:00Z")["produced_at"]
    assert isinstance(value, str)
    assert value == "2026-07-25T09:55:00Z"


def test_indentless_sequence_of_flat_mappings():
    """PyYAML's default dump style: dashes at the parent key's indent."""
    doc = ("consumes:\n"
           "- artifact: intent\n"
           "  hash: sha256:aaaa\n"
           "- artifact: diff\n"
           "  hash: git:263e2221f7ddde8b9f9f0138762de1d116b4d8c0\n")
    assert miniyaml.loads(doc) == {"consumes": [
        {"artifact": "intent", "hash": "sha256:aaaa"},
        {"artifact": "diff",
         "hash": "git:263e2221f7ddde8b9f9f0138762de1d116b4d8c0"},
    ]}


def test_indented_sequence_of_scalars():
    doc = "artifact_sections:\n  - Problem statement\n  - Goals\n"
    assert miniyaml.loads(doc) == {
        "artifact_sections": ["Problem statement", "Goals"]}


def test_flow_sequences():
    assert miniyaml.loads("consumes: [request]") == {"consumes": ["request"]}
    assert miniyaml.loads("backward: []") == {"backward": []}
    assert miniyaml.loads("escalations: [E1, E2, E3]") == {
        "escalations": ["E1", "E2", "E3"]}


def test_scalar_types():
    doc = ("a: true\nb: false\nc: null\nd: ~\ne:\nf: 42\ng: -7\n"
           "h: 'single quoted'\ni: \"double \\\"quoted\\\"\"\nj: plain text\n")
    assert miniyaml.loads(doc) == {
        "a": True, "b": False, "c": None, "d": None, "e": None,
        "f": 42, "g": -7, "h": "single quoted", "i": 'double "quoted"',
        "j": "plain text",
    }


def test_floats_stay_plain_strings():
    """No pipeline field is a float; scalar typing stays closed."""
    assert miniyaml.loads("x: 1.5") == {"x": "1.5"}


def test_inline_comment_outside_quotes():
    doc = "bypass: false          # retired (D22); the entry gate is computed\n"
    assert miniyaml.loads(doc) == {"bypass": False}


def test_hash_inside_value_is_not_a_comment():
    assert miniyaml.loads("url: http://x/#frag") == {"url": "http://x/#frag"}
    assert miniyaml.loads("s: 'a # b'") == {"s": "a # b"}


def test_full_line_comments_and_blanks():
    doc = "# header comment\n\na: 1\n\n# trailing\n"
    assert miniyaml.loads(doc) == {"a": 1}


def test_plain_scalar_continuation_folds_with_single_space():
    """PyYAML's width=88 folding wrapped long ledger values; they must
    fold back."""
    doc = ("- step: \"2\"\n"
           "  what: bound the contextvar in the middleware rather than a separate\n"
           "    logging filter module\n"
           "  why: short\n")
    entries = miniyaml.loads(doc)
    assert entries[0]["what"] == ("bound the contextvar in the middleware "
                                  "rather than a separate logging filter module")
    assert entries[0]["why"] == "short"


def test_nested_block_mapping_with_sequence():
    doc = ("floor:\n"
           "  governed_paths:\n"
           "    - .dev/config.yaml\n"
           "    - '**/auth/**'\n"
           "  max_files: 3\n")
    assert miniyaml.loads(doc) == {"floor": {
        "governed_paths": [".dev/config.yaml", "**/auth/**"],
        "max_files": 3,
    }}


def test_empty_document_is_none():
    assert miniyaml.loads("") is None
    assert miniyaml.loads("\n# only a comment\n") is None


def test_top_level_sequence_and_empty_collections():
    assert miniyaml.loads("[]") == []
    assert miniyaml.loads("{}") == {}
    assert miniyaml.loads("- a\n- b\n") == ["a", "b"]


def test_top_level_scalar_is_returned_as_is():
    """artifact.py depends on this: a non-mapping frontmatter must come
    back as the parsed value so 'must be a mapping' can fire."""
    assert miniyaml.loads("just a scalar") == "just a scalar"
    assert miniyaml.loads("- a\n") == ["a"]


# --- error vectors: outside the subset fails loudly -------------------

@pytest.mark.parametrize("doc,fragment", [
    ("m: {a: 1}", "flow mapping"),
    ("a: &anchor 1", "unsupported YAML construct"),
    ("a: *alias", "unsupported YAML construct"),
    ("a: !!str x", "unsupported YAML construct"),
    ("a: |\n  block", "unsupported YAML construct"),
    ("a: >\n  folded", "unsupported YAML construct"),
    ("a: 'unterminated", "unterminated single-quoted"),
    ('a: "unterminated', "unterminated double-quoted"),
    ("a: [1, 2", "unterminated flow sequence"),
    ("a: [[1]]", "nested flow collections"),
    ("a: 1\na: 2", "duplicate key"),
    ("\ta: 1", "tabs are not allowed"),
])
def test_unsupported_constructs_raise_typed(doc, fragment):
    with pytest.raises(MiniYamlError) as exc:
        miniyaml.loads(doc)
    assert fragment in str(exc.value)


def test_errors_carry_line_numbers():
    with pytest.raises(MiniYamlError) as exc:
        miniyaml.loads("ok: 1\nbad: {x: 1}\n")
    assert "line 2" in str(exc.value)


# --- dumper vectors ---------------------------------------------------

def test_dump_matches_fixture_frontmatter_style():
    fm = {
        "pipeline": 1,
        "contract": "review",
        "task": "T-2026-07-25-request-id-header",
        "produced_at": "2026-07-25T09:55:00Z",
        "consumes": [
            {"artifact": "intent", "hash": "sha256:aaaa"},
            {"artifact": "diff",
             "hash": "git:263e2221f7ddde8b9f9f0138762de1d116b4d8c0"},
        ],
    }
    assert miniyaml.dumps(fm) == (
        "pipeline: 1\n"
        "contract: review\n"
        "task: T-2026-07-25-request-id-header\n"
        "produced_at: 2026-07-25T09:55:00Z\n"
        "consumes:\n"
        "- artifact: intent\n"
        "  hash: sha256:aaaa\n"
        "- artifact: diff\n"
        "  hash: git:263e2221f7ddde8b9f9f0138762de1d116b4d8c0\n"
    )


def test_dump_quotes_only_when_needed():
    out = miniyaml.dumps({
        "a": "plain", "b": "123", "c": "true", "d": "", "e": "1.5",
        "f": "has: colon space", "g": "ends with space ",
    })
    assert out == ('a: plain\nb: "123"\nc: "true"\nd: ""\ne: "1.5"\n'
                   'f: "has: colon space"\ng: "ends with space "\n')


def test_dump_empty_collections():
    assert miniyaml.dumps([]) == "[]\n"
    assert miniyaml.dumps({}) == "{}\n"
    assert miniyaml.dumps({"consumes": []}) == "consumes: []\n"


def test_dump_rejects_unserializable():
    with pytest.raises(MiniYamlError):
        miniyaml.dumps({"x": 1.5})
    with pytest.raises(MiniYamlError):
        miniyaml.dumps({"x": object()})


# --- round-trip property over every real document ---------------------

def _real_documents():
    docs = []
    for path in sorted(list(FIXTURES.glob("*/*/*.md"))
                       + list((ROOT / "contracts").glob("*.md"))):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if not text.startswith("---\n"):
            continue
        lines = text.split("\n")
        close = next((i for i in range(1, len(lines))
                      if lines[i].rstrip() == "---"), None)
        if close is None:
            continue
        docs.append((f"{path.name}:frontmatter",
                     "\n".join(lines[1:close])))
        m = re.search(r"## Entries\s*\n```(?:yaml)?\n(.*?)\n?```",
                      text, re.DOTALL)
        if m:
            docs.append((f"{path.name}:ledger", m.group(1)))
    assert len(docs) >= 15, "fixture/contract corpus went missing"
    return docs


@pytest.mark.parametrize("name,doc",
                         _real_documents(),
                         ids=[n for n, _ in _real_documents()])
def test_round_trip_over_real_corpus(name, doc):
    data = miniyaml.loads(doc)
    assert miniyaml.loads(miniyaml.dumps(data)) == data


def test_pyyaml_parity_over_real_corpus():
    """Cross-check against PyYAML where available (dev machines); the
    only tolerated difference is timestamp typing."""
    yaml = pytest.importorskip("yaml")
    import datetime

    def norm(v):
        if isinstance(v, datetime.datetime):
            s = v.isoformat()
            return s.replace("+00:00", "Z")
        if isinstance(v, datetime.date):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v

    for name, doc in _real_documents():
        assert miniyaml.loads(doc) == norm(yaml.safe_load(doc)), name


def test_parse_scalar_for_frontmatter_set():
    assert miniyaml.parse_scalar("1") == 1
    assert miniyaml.parse_scalar("intent") == "intent"
    assert miniyaml.parse_scalar("true") is True
    assert miniyaml.parse_scalar("null") is None
    assert miniyaml.parse_scalar("'quoted'") == "quoted"
    assert miniyaml.parse_scalar("2026-07-25T09:55:00Z") == "2026-07-25T09:55:00Z"
