#!/usr/bin/env python3
# Sole entry point for the reins deterministic core (D30, named in D32).
#
# Invoked by path, never installed:
#
#     python3 ~/.claude/pipeline/core/pipeline_cli.py <subcommand> ...
#
# Self-locating: realpath resolves the ~/.claude symlink chain to the
# real checkout, so the `pipeline` package is imported from its own repo
# regardless of caller cwd, PATH, PYTHONPATH, or virtualenv.
#
# This file must stay parseable by very old interpreters so the version
# guard below can print a readable message instead of a SyntaxError:
# no f-strings' nesting tricks, no walrus, no match, no type syntax.

import os
import sys

if sys.version_info < (3, 9):
    sys.stderr.write(
        "reins requires Python >= 3.9 (this interpreter is %s).\n"
        "Invoke with a newer python3, e.g.: python3.9 %s ...\n"
        % (sys.version.split()[0], os.path.basename(__file__)))
    sys.exit(1)  # exit 1 = usage error, per the 0/1/2/3 contract

_HERE = os.path.dirname(os.path.realpath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pipeline.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
