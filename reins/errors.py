"""Typed error hierarchy for the contract pipeline.

Every error raised by the deterministic core derives from PipelineError so
runtimes can catch one type at the boundary. Parsing errors carry the file
path and, where known, a line number, so skills can quote them verbatim
when self-correcting.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for all pipeline errors."""


class ArtifactParseError(PipelineError):
    """The file is not a structurally valid pipeline artifact.

    Raised for: missing/unterminated frontmatter, non-mapping frontmatter,
    invalid YAML, duplicate section headings, undecodable bytes.
    Parsing is all-or-nothing: no partially parsed Artifact ever escapes.
    """

    def __init__(self, path: str, message: str, line: int | None = None):
        self.path = str(path)
        self.message = message
        self.line = line
        loc = f"{self.path}:{line}" if line is not None else self.path
        super().__init__(f"{loc}: {message}")


class SchemaError(PipelineError):
    """The schema registry itself is inconsistent (a programming error,

    surfaced by tests, never expected at runtime)."""


class LedgerFormatError(PipelineError):
    """ledger.md Entries block is not a valid list of entry mappings."""

    def __init__(self, path: str, message: str):
        self.path = str(path)
        self.message = message
        super().__init__(f"{self.path}: {message}")
