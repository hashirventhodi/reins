"""Restricted YAML subset parser and canonical dumper (stdlib only).

This module replaces PyYAML (D30). It implements exactly the subset the
pipeline reads and writes — nothing more:

  - block mappings (nested), with plain keys
  - block sequences of scalars or of flat mappings; the dash may sit at
    the parent key's indent (PyYAML's default) or deeper (contract files)
  - flow sequences of scalars only, including ``[]``
  - scalars: plain strings, single-quoted, double-quoted (backslash
    escapes), integers, ``true``/``false``, ``null``/``~``/empty
  - full-line and inline comments (`` #`` outside quotes)
  - multi-line plain-scalar continuations (PyYAML's ``width=88`` folding
    wrapped long values in existing artifacts; they fold back with a
    single space)

Deliberate divergences from PyYAML:

  - Timestamps are plain strings, never ``datetime`` objects. PyYAML's
    implicit timestamp resolution caused D26 (a space-separated datetime
    re-serialization sorted before ``T`` and broke RETURNED clearing);
    keeping them as strings removes the bug class.
  - Floats are plain strings. No pipeline field is a float; treating
    them as strings keeps scalar typing closed (str | int | bool | None).

Everything outside the subset — flow mappings, anchors, aliases, tags,
block scalars — raises :class:`MiniYamlError` with a line number. The
failure mode is loud and typed, never a silent misparse.
"""

from __future__ import annotations

import re

__all__ = ["MiniYamlError", "loads", "dumps", "parse_scalar"]


class MiniYamlError(ValueError):
    """A document strayed outside the supported subset."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


_INT_RE = re.compile(r"^[-+]?\d+$")
_KEY_RE = re.compile(r"^(?P<key>[^\s:#'\"{}\[\]&*!|>%@`][^:#]*?):(?:[ \t]+(?P<value>.*))?$")
_COMMENT_RE = re.compile(r"(?:^|\s)#")
_BOOL_NULL = {
    "true": True, "True": True, "TRUE": True,
    "false": False, "False": False, "FALSE": False,
    "null": None, "Null": None, "NULL": None, "~": None,
}


def _strip_comment(text: str) -> str:
    """Drop an inline comment: the first ``#`` at start or after
    whitespace, outside single/double quotes."""
    in_single = in_double = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_single:
            if c == "'":
                in_single = False
        elif in_double:
            if c == "\\":
                i += 1
            elif c == '"':
                in_double = False
        elif c == "'":
            in_single = True
        elif c == '"':
            in_double = True
        elif c == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
        i += 1
    return text.rstrip()


def parse_scalar(text: str, line: int | None = None):
    """Parse a single scalar. Exported for ``frontmatter --set``."""
    text = text.strip()
    if text == "":
        return None
    if text in _BOOL_NULL:
        return _BOOL_NULL[text]
    if _INT_RE.match(text):
        return int(text)
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            raise MiniYamlError("unterminated single-quoted scalar", line)
        body = text[1:-1]
        if re.search(r"(?<!')'(?!')", body):
            raise MiniYamlError("garbage after single-quoted scalar", line)
        return body.replace("''", "'")
    if text.startswith('"'):
        m = re.match(r'^"((?:[^"\\]|\\.)*)"$', text)
        if not m:
            raise MiniYamlError("unterminated double-quoted scalar", line)
        return (
            m.group(1)
            .replace("\\\\", "\x00")
            .replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace("\x00", "\\")
        )
    if text[0] in "&*!|>%@`":
        raise MiniYamlError(
            f"unsupported YAML construct starting with {text[0]!r} "
            "(anchors, aliases, tags and block scalars are outside the "
            "supported subset)", line)
    if text == "{}":
        return {}
    if text.startswith("{"):
        raise MiniYamlError("flow mappings are outside the supported subset", line)
    return text


def _parse_flow_seq(text: str, line: int | None):
    inner = text[1:-1].strip()
    if not inner:
        return []
    items = []
    for part in inner.split(","):
        part = part.strip()
        if part.startswith(("[", "{")):
            raise MiniYamlError("nested flow collections are unsupported", line)
        if part == "":
            raise MiniYamlError("empty element in flow sequence", line)
        items.append(parse_scalar(part, line))
    return items


class _Lines:
    """The document as (indent, content, lineno) triples, comments and
    blank lines removed."""

    def __init__(self, text: str):
        self.rows: list[tuple[int, str, int]] = []
        for n, raw in enumerate(text.split("\n"), start=1):
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise MiniYamlError("tabs are not allowed in indentation", n)
            stripped = _strip_comment(raw)
            if not stripped.strip():
                continue
            indent = len(stripped) - len(stripped.lstrip(" "))
            self.rows.append((indent, stripped.strip(), n))
        self.i = 0

    def peek(self):
        return self.rows[self.i] if self.i < len(self.rows) else None

    def next(self):
        row = self.rows[self.i]
        self.i += 1
        return row


def _value_from_inline(text: str, line: int):
    """Parse an inline value: flow seq, or scalar."""
    if text.startswith("["):
        if not text.endswith("]"):
            raise MiniYamlError("unterminated flow sequence", line)
        return _parse_flow_seq(text, line)
    return parse_scalar(text, line)


def _fold_continuations(lines: _Lines, indent: int, first: str, line: int) -> str:
    """Fold deeper-indented plain-scalar continuation lines with spaces."""
    parts = [first]
    while True:
        row = lines.peek()
        if row is None or row[0] <= indent:
            break
        _, content, n = lines.next()
        if content.startswith(("- ", "-")) and (content == "-" or content[1:2] == " "):
            raise MiniYamlError(
                "sequence item where a scalar continuation was expected", n)
        parts.append(content)
    return " ".join(parts)


def _parse_node(lines: _Lines, min_indent: int):
    row = lines.peek()
    if row is None:
        return None
    indent, content, line = row
    if content == "-" or content.startswith("- "):
        return _parse_sequence(lines, indent)
    if _KEY_RE.match(content):
        return _parse_mapping(lines, indent)
    lines.next()
    if content.startswith("["):
        if not content.endswith("]"):
            raise MiniYamlError("unterminated flow sequence", line)
        return _parse_flow_seq(content, line)
    value = parse_scalar(content, line)
    if isinstance(value, str):
        folded = _fold_continuations(lines, indent, content, line)
        return parse_scalar(folded, line) if folded != content else value
    return value


def _parse_sequence(lines: _Lines, indent: int):
    items = []
    while True:
        row = lines.peek()
        if row is None or row[0] != indent:
            break
        _, content, line = row
        if not (content == "-" or content.startswith("- ")):
            break
        lines.next()
        rest = content[1:].strip()
        if rest == "":
            nxt = lines.peek()
            if nxt is not None and nxt[0] > indent:
                items.append(_parse_node(lines, nxt[0]))
            else:
                items.append(None)
        elif _KEY_RE.match(rest):
            item_indent = indent + (len(content) - len(rest))
            items.append(_parse_inline_mapping(lines, item_indent, rest, line))
        else:
            if rest.startswith("["):
                items.append(_value_from_inline(rest, line))
            else:
                folded = _fold_continuations(lines, indent, rest, line)
                items.append(parse_scalar(folded, line))
    return items


def _parse_inline_mapping(lines: _Lines, indent: int, first: str, line: int):
    """A mapping whose first ``key: value`` sits on a dash line; the
    remaining keys follow at ``indent``."""
    mapping: dict = {}
    _consume_pair(lines, mapping, indent, first, line)
    while True:
        row = lines.peek()
        if row is None or row[0] != indent:
            break
        _, content, n = row
        if content == "-" or content.startswith("- ") or not _KEY_RE.match(content):
            break
        lines.next()
        _consume_pair(lines, mapping, indent, content, n)
    return mapping


def _parse_mapping(lines: _Lines, indent: int):
    mapping: dict = {}
    while True:
        row = lines.peek()
        if row is None or row[0] != indent:
            break
        _, content, line = row
        if content == "-" or content.startswith("- "):
            break
        if not _KEY_RE.match(content):
            raise MiniYamlError(f"expected 'key: value', got {content!r}", line)
        lines.next()
        _consume_pair(lines, mapping, indent, content, line)
    return mapping


def _consume_pair(lines: _Lines, mapping: dict, indent: int, content: str, line: int):
    m = _KEY_RE.match(content)
    if not m:
        raise MiniYamlError(f"expected 'key: value', got {content!r}", line)
    key = m.group("key").strip()
    if key.startswith(("'", '"')):
        key = parse_scalar(key, line)
    if key in mapping:
        raise MiniYamlError(f"duplicate key {key!r}", line)
    raw_value = m.group("value")
    if raw_value is None or raw_value == "":
        nxt = lines.peek()
        if nxt is not None and nxt[0] > indent:
            mapping[key] = _parse_node(lines, nxt[0])
        elif (nxt is not None and nxt[0] == indent
              and (nxt[1] == "-" or nxt[1].startswith("- "))):
            # PyYAML's indentless sequence: dashes at the key's own indent.
            mapping[key] = _parse_sequence(lines, indent)
        else:
            mapping[key] = None
        return
    raw_value = raw_value.strip()
    if raw_value.startswith("["):
        mapping[key] = _value_from_inline(raw_value, line)
        return
    value = parse_scalar(raw_value, line)
    if isinstance(value, str):
        folded = _fold_continuations(lines, indent, raw_value, line)
        if folded != raw_value:
            value = parse_scalar(folded, line)
    mapping[key] = value


def loads(text: str):
    """Parse a document. Returns dict, list, scalar, or None (empty)."""
    lines = _Lines(text)
    if lines.peek() is None:
        return None
    result = _parse_node(lines, 0)
    row = lines.peek()
    if row is not None:
        raise MiniYamlError(
            f"unexpected content after document: {row[1]!r}", row[2])
    return result


# --- dumper -----------------------------------------------------------

_PLAIN_SAFE_RE = re.compile(r"^[^\s\-?:,\[\]{}#&*!|>'\"%@`]([^:#]|:(?!\s)|(?<!\s)#)*$")
_FLOAT_LIKE_RE = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+[eE][-+]?\d+)$")


def _needs_quote(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if "\n" in s or any(ord(c) < 32 for c in s):
        return True
    if s in _BOOL_NULL or _INT_RE.match(s) or _FLOAT_LIKE_RE.match(s):
        return True
    if s == "-" or s.startswith("- "):
        return True
    return not _PLAIN_SAFE_RE.match(s)


def _dump_scalar(v) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        if _needs_quote(v):
            escaped = (v.replace("\\", "\\\\").replace('"', '\\"')
                        .replace("\n", "\\n").replace("\t", "\\t"))
            return f'"{escaped}"'
        return v
    raise MiniYamlError(f"cannot serialize {type(v).__name__}")


def _dump_node(v, indent: int, out: list) -> None:
    pad = " " * indent
    if isinstance(v, dict):
        for key, val in v.items():
            k = _dump_scalar(key) if isinstance(key, str) else _dump_scalar(key)
            if isinstance(val, dict) and val:
                out.append(f"{pad}{k}:")
                _dump_node(val, indent + 2, out)
            elif isinstance(val, list) and val:
                out.append(f"{pad}{k}:")
                _dump_node(val, indent, out)
            elif isinstance(val, dict):
                out.append(f"{pad}{k}: {{}}")
            elif isinstance(val, list):
                out.append(f"{pad}{k}: []")
            else:
                out.append(f"{pad}{k}: {_dump_scalar(val)}")
    elif isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and item:
                first = True
                for key, val in item.items():
                    if isinstance(val, (dict, list)) and val:
                        raise MiniYamlError(
                            "nested collections inside sequence items are "
                            "outside the supported subset")
                    rendered = (f"{_dump_scalar(key)}: "
                                f"{_dump_scalar(val) if not isinstance(val, (dict, list)) else ('{}' if isinstance(val, dict) else '[]')}")
                    if first:
                        out.append(f"{pad}- {rendered}")
                        first = False
                    else:
                        out.append(f"{pad}  {rendered}")
            elif isinstance(item, list):
                raise MiniYamlError(
                    "sequences of sequences are outside the supported subset")
            elif isinstance(item, dict):
                out.append(f"{pad}- {{}}")
            else:
                out.append(f"{pad}- {_dump_scalar(item)}")
    else:
        out.append(f"{pad}{_dump_scalar(v)}")


def dumps(obj) -> str:
    """Serialize canonically: insertion-order keys, block style, dashes
    at the parent key's indent, no line wrapping, quote only when a
    plain rendering would re-parse differently. Ends with a newline."""
    if isinstance(obj, list) and not obj:
        return "[]\n"
    if isinstance(obj, dict) and not obj:
        return "{}\n"
    out: list = []
    _dump_node(obj, 0, out)
    return "\n".join(out) + "\n"
