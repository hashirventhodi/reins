"""Deterministic core of the contract pipeline (the product).

Public modules: schemas, artifact, errors (M0); validate, frontier,
decisions, telemetry, cli follow in M1-M4. Nothing in this package may
reference any runtime binding (see blueprint D9).
"""

from .schemas import PIPELINE_VERSION  # noqa: F401
