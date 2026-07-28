"""Floor policy: presets, resolution, and repo-fit auditing (D39).

A starter policy that every repo is "expected to edit" is a policy nobody
edits. Shipped as a static template it fails in three measurable ways,
all observed on a real monorepo: patterns that match nothing in this repo
(`**/go.mod` in a TypeScript shop), sensitive directories matched by
nothing (`backend-core/auth-service/` slips past `**/auth/**`), and
limits so tight that every change lands in `full`, which makes the floor
noise rather than a control.

The design follows three proven mechanisms:

**Presets over templates** — Renovate's `extends` model. A repo names the
bundles it wants (`extends: [reins:base, reins:node]`) instead of
inheriting forty copy-pasted globs. Bundles improve centrally, and a
reader can trace where any rule came from.

**Propose, never write** — Renovate onboards by opening a pull request
proposing a config, which a human merges. Nothing here writes policy on
its own, for a reason stronger than convention: the floor is the agent's
own oversight bar, and an agent that can widen it silently is an agent
with no bar at all (D18).

**Report fit, do not fit blindly** — deriving config from history is
accepted practice (CODEOWNERS generators do it from `git log`), but the
limits are the one place it must not be applied naively. Peer review
research (SmartBear/Cisco, ~2,500 reviews) puts effective review at
200-400 lines, with defect detection falling from ~87% under 100 lines
to ~28% past 1,000. So a repo whose median change touches 22 files is
not a repo that needs a higher bar — it is a repo where most changes
genuinely are not small. Auto-fitting the limits to that would ratify
it. Instead :func:`limit_fit` reports what share of real changes would
qualify for the cheap lane and lets a human decide with both their own
numbers and the research in view.

Everything here is pure: facts (repository paths, commit samples) are
supplied by the runtime, which owns git (D12).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .floor import DEFAULT_MAX_FILES, DEFAULT_MAX_LINES, matches

__all__ = [
    "Preset", "PRESETS", "PRESET_PREFIX", "REVIEW_EFFECTIVE_LINES",
    "detect", "resolve", "dead_patterns", "ungoverned_markers",
    "limit_fit", "audit", "propose",
]

PRESET_PREFIX = "reins:"

# SmartBear/Cisco peer-review study: effectiveness peaks in this band.
REVIEW_EFFECTIVE_LINES = (200, 400)


@dataclass(frozen=True)
class Preset:
    """A named bundle of governed paths.

    `markers` are globs whose presence in a repository suggests the
    preset applies; they are a detection hint only and never govern
    anything themselves.
    """

    name: str
    why: str
    governed_paths: tuple = ()
    markers: tuple = ()


def _p(name, why, governed_paths, markers=()):
    return Preset(name=name, why=why, governed_paths=tuple(governed_paths),
                  markers=tuple(markers))


PRESETS: dict = {p.name: p for p in [
    _p("base",
       "surfaces where a small diff is rarely a small risk, in any stack",
       [".dev/config.yaml", ".github/**", "**/secrets/**", "**/crypto/**"]),
    _p("auth",
       "authentication and authorization, however the directory is named",
       ["**/auth/**", "**/*auth-service*/**", "**/*identity*/**",
        "**/*session*/**", "**/*permission*/**"],
       ["**/auth/**", "**/*auth*/**", "**/*identity*/**"]),
    _p("database",
       "schema changes are irreversible in a way code changes are not",
       ["**/migrations/**", "**/migration/**", "**/schema.prisma",
        "**/alembic/**"],
       ["**/migrations/**", "**/migration/**", "**/schema.prisma",
        "**/alembic/**"]),
    _p("api-contracts",
       "cross-service contracts: a field rename here breaks callers silently",
       ["**/*.proto", "**/openapi*.yaml", "**/openapi*.yml",
        "**/openapi*.json", "**/*.graphql"],
       ["**/*.proto", "**/openapi*.yaml", "**/openapi*.yml",
        "**/*.graphql"]),
    _p("infra",
       "infrastructure and gateway routing: blast radius is the whole system",
       ["**/infra/**", "**/terraform/**", "**/*.tf", "**/helm/**",
        "**/k8s/**", "**/kubernetes/**", "**/traefik/**", "**/nginx/**"],
       ["**/infra/**", "**/terraform/**", "**/*.tf", "**/helm/**",
        "**/k8s/**", "**/traefik/**"]),
    _p("containers",
       "image and compose changes alter what actually runs",
       ["**/Dockerfile", "**/Dockerfile.*", "**/docker-compose*.yml",
        "**/docker-compose*.yaml"],
       ["**/Dockerfile", "**/docker-compose*.yml"]),
    _p("node",
       "dependency and build surface for JavaScript/TypeScript",
       ["**/package.json", "**/pnpm-workspace.yaml", "**/turbo.json"],
       ["**/package.json"]),
    _p("python",
       "dependency and build surface for Python",
       ["**/pyproject.toml", "**/requirements*.txt", "**/setup.py"],
       ["**/pyproject.toml", "**/requirements*.txt", "**/setup.py"]),
    _p("go", "dependency surface for Go",
       ["**/go.mod"], ["**/go.mod"]),
    _p("rust", "dependency surface for Rust",
       ["**/Cargo.toml"], ["**/Cargo.toml"]),
    _p("shared-libs",
       "code many services import: a bad change fans out to all of them",
       ["**/shared/**", "**/packages/common/**", "**/libs/**"],
       ["**/shared/**", "**/packages/common/**", "**/libs/**"]),
]}


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(matches(path, pat) for pat in patterns)


def detect(paths: Sequence[str]) -> list:
    """Preset names whose markers appear in `paths`. `base` is always in.

    Build outputs are excluded so that `dist/auth/...` does not make a
    repository look like it has an auth service.
    """
    real = [p for p in paths if not _is_build_output(p)]
    found = ["base"]
    for name, preset in PRESETS.items():
        if name == "base" or not preset.markers:
            continue
        if any(_matches_any(p, preset.markers) for p in real):
            found.append(name)
    return sorted(found)


_BUILD_DIRS = ("dist", "build", "node_modules", "target", ".venv",
               "__pycache__", "vendor", ".git", "coverage", ".next")


def _is_build_output(path: str) -> bool:
    return any(seg in _BUILD_DIRS for seg in path.split("/"))


def resolve(config) -> dict:
    """Expand a `.dev/config.yaml` mapping into an effective floor policy.

    `extends: [reins:base, reins:node]` contributes governed paths;
    a local `floor:` block adds its own and sets the limits. Order is
    preserved and duplicates dropped, so the result is deterministic and
    readable. Unknown preset names raise rather than being skipped: a
    silently ignored preset is a control the reader believes is on.
    """
    config = config if isinstance(config, dict) else {}
    local = config.get("floor")
    local = local if isinstance(local, dict) else {}
    paths: list = []
    used: list = []
    for ref in config.get("extends") or []:
        if not isinstance(ref, str) or not ref.startswith(PRESET_PREFIX):
            raise ValueError(
                f"unknown preset reference {ref!r}: expected "
                f"'{PRESET_PREFIX}<name>'")
        name = ref[len(PRESET_PREFIX):]
        preset = PRESETS.get(name)
        if preset is None:
            raise ValueError(
                f"unknown preset {ref!r}; available: "
                + ", ".join(PRESET_PREFIX + n for n in sorted(PRESETS)))
        used.append(name)
        paths.extend(preset.governed_paths)
    paths.extend(local.get("governed_paths") or [])
    seen = set()
    governed = [p for p in paths if not (p in seen or seen.add(p))]
    return {
        "governed_paths": governed,
        "max_files": local.get("max_files", DEFAULT_MAX_FILES),
        "max_lines": local.get("max_lines", DEFAULT_MAX_LINES),
        "presets": used,
    }


def dead_patterns(patterns: Sequence[str], paths: Sequence[str]) -> list:
    """Globs that match nothing in this repository.

    Applied to *locally authored* patterns only. A preset's patterns are
    deliberately exempt: `**/secrets/**` matching nothing is the desired
    state, not a defect, and the actionable unit for preset-supplied
    rules is the preset itself (see `presets_unnecessary`). ESLint
    reports the same condition for ignore patterns that match no files,
    for the same reason — a rule that cannot fire reads like a control
    without being one.
    """
    real = [p for p in paths if not _is_build_output(p)]
    return [pat for pat in patterns
            if not any(matches(p, pat) for p in real)]


def ungoverned_markers(paths: Sequence[str], policy_paths: Sequence[str]
                       ) -> list:
    """Preset-detected sensitive areas this policy does not cover.

    This is the check that catches an `auth-service/` slipping past
    `**/auth/**`. Returns ``[{preset, why, governed_paths, examples}]``.
    """
    real = [p for p in paths if not _is_build_output(p)]
    gaps = []
    for name in detect(real):
        preset = PRESETS[name]
        examples = sorted({p for p in real
                           if _matches_any(p, preset.markers or
                                           preset.governed_paths)
                           and not _matches_any(p, policy_paths)})
        if examples:
            gaps.append({"preset": name, "why": preset.why,
                         "governed_paths": list(preset.governed_paths),
                         "examples": examples[:5],
                         "ungoverned_files": len(examples)})
    return gaps


def _percentile(values: Sequence[int], pct: float):
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[k]


def limit_fit(samples: Sequence[dict], max_files: int, max_lines: int) -> dict:
    """How the configured limits meet this repository's real changes.

    `samples` are ``{"files": n, "lines": n}`` per recent change, supplied
    by the runtime from git. Reports the distribution, the share of
    changes that would qualify for the express lane, and the peer-review
    band the limits should be read against.

    It deliberately does not recommend "set the limits to your median".
    A repository whose changes are routinely large does not need a higher
    bar; that is what the bar is for. What a human needs to decide well
    is the express share and the review-effectiveness cost — both are
    here, neither is acted on.
    """
    files = [int(s.get("files", 0)) for s in samples]
    lines = [int(s.get("lines", 0)) for s in samples]
    qualifying = sum(1 for s in samples
                     if int(s.get("files", 0)) <= max_files
                     and int(s.get("lines", 0)) <= max_lines)
    total = len(samples)
    low, high = REVIEW_EFFECTIVE_LINES
    return {
        "samples": total,
        "files": {"p50": _percentile(files, 50), "p90": _percentile(files, 90),
                  "max": max(files) if files else None},
        "lines": {"p50": _percentile(lines, 50), "p90": _percentile(lines, 90),
                  "max": max(lines) if lines else None},
        "limits": {"max_files": max_files, "max_lines": max_lines},
        "express_share": round(qualifying / total, 3) if total else None,
        "express_qualifying": qualifying,
        "review_effective_lines": [low, high],
        "notes": _limit_notes(qualifying, total, max_lines, low, high),
    }


def _limit_notes(qualifying: int, total: int, max_lines: int,
                 low: int, high: int) -> list:
    notes = []
    if not total:
        return ["no change samples supplied; limits cannot be assessed"]
    share = qualifying / total
    if share == 0:
        notes.append(
            "no sampled change would take the express lane: the lane is "
            "inert here. Either these changes genuinely are not small — "
            "which is the floor working — or the limits are too tight.")
    elif share < 0.1:
        notes.append(
            f"only {share:.0%} of sampled changes would take the express "
            "lane; check that is the intent and not an accident.")
    elif share > 0.9:
        notes.append(
            f"{share:.0%} of sampled changes would take the express lane; "
            "a floor that almost never triggers is close to no floor.")
    if max_lines > high:
        notes.append(
            f"max_lines {max_lines} is above the {low}-{high} line band "
            "where peer review is most effective (defect detection falls "
            "from ~87% under 100 lines to ~28% past 1,000), so express "
            "would cover changes a reviewer is measurably worse at.")
    return notes


def audit(config, paths: Sequence[str], samples: Sequence[dict] = ()) -> dict:
    """The complete repo-fit report for an existing policy.

    Every field is actionable: a preset to add, a preset to drop, a
    hand-written pattern that can never fire, an area left ungoverned,
    or a limit to weigh. Nothing here changes anything.
    """
    config = config if isinstance(config, dict) else {}
    local = config.get("floor")
    local = local if isinstance(local, dict) else {}
    effective = resolve(config)
    governed = effective["governed_paths"]
    detected = detect(paths)
    in_use = effective["presets"]
    return {
        "presets_in_use": in_use,
        "presets_detected": detected,
        "presets_missing": [n for n in detected if n not in in_use],
        "presets_unnecessary": [n for n in in_use
                                if n != "base" and n not in detected],
        "dead_patterns": dead_patterns(
            list(local.get("governed_paths") or []), paths),
        "coverage_gaps": ungoverned_markers(paths, governed),
        "limits": limit_fit(samples, effective["max_files"],
                            effective["max_lines"]),
    }


def propose(paths: Sequence[str], samples: Sequence[dict] = ()) -> dict:
    """A policy proposal for a repository — never written, only offered.

    Presets come from what the repository actually contains, so there are
    no dead patterns by construction. Limits are the shipped defaults:
    they are a review-effectiveness judgment, not a property of the
    repository, and moving them is exactly the decision a human should
    make in front of the numbers in ``limits``.
    """
    detected = detect(paths)
    return {
        "extends": [PRESET_PREFIX + n for n in detected],
        "rationale": {n: PRESETS[n].why for n in detected},
        "floor": {"max_files": DEFAULT_MAX_FILES,
                  "max_lines": DEFAULT_MAX_LINES},
        "limits": limit_fit(samples, DEFAULT_MAX_FILES, DEFAULT_MAX_LINES),
    }
