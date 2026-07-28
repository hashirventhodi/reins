"""Floor policy presets, resolution and repo-fit auditing (D39).

The module is pure, so these are unit tests over supplied facts. What
matters is not that it reports things but *which* things: every field of
the audit must be something a human can act on, and nothing in here may
ever change a policy on its own.
"""

from __future__ import annotations

import pytest

from reins import policy
from reins.floor import DEFAULT_MAX_FILES, DEFAULT_MAX_LINES

# A monorepo shaped like the one that produced this decision: an auth
# service whose directory is not called `auth/`, cross-service protos,
# gateway config, a shared library, two language ecosystems, and build
# output that must not be mistaken for source.
MONOREPO = [
    "backend-core/auth-service/src/jwt.ts",
    "backend-core/shared/src/index.ts",
    "backend-core/orders/src/migrations/001-init.ts",
    "backend-ai/pyproject.toml",
    "web/package.json",
    "proto/order.proto",
    "traefik/traefik.yml",
    "docker-compose.yml",
    "services/api/Dockerfile",
    ".github/workflows/ci.yml",
    "README.md",
    "shared/dist/auth/bundle.js",          # build output
    "web/node_modules/left-pad/index.js",  # dependency
]


# --- detection --------------------------------------------------------

def test_detects_the_stacks_a_repo_actually_contains():
    found = policy.detect(MONOREPO)
    for expected in ("base", "auth", "database", "api-contracts", "infra",
                     "containers", "node", "python", "shared-libs"):
        assert expected in found, expected
    for absent in ("go", "rust"):
        assert absent not in found, absent


def test_detection_ignores_build_output():
    """`dist/auth/bundle.js` must not make a repo look like it has an
    auth service, or every JS repo would 'have' one."""
    assert "auth" not in policy.detect(["web/dist/auth/bundle.js",
                                        "web/node_modules/x/auth/y.js"])
    assert policy.detect(["README.md"]) == ["base"]


def test_base_is_always_detected():
    assert "base" in policy.detect([])


# --- resolution -------------------------------------------------------

def test_extends_expands_into_governed_paths():
    resolved = policy.resolve({"extends": ["reins:base", "reins:node"]})
    assert ".github/**" in resolved["governed_paths"]
    assert "**/package.json" in resolved["governed_paths"]
    assert resolved["presets"] == ["base", "node"]
    assert resolved["max_files"] == DEFAULT_MAX_FILES
    assert resolved["max_lines"] == DEFAULT_MAX_LINES


def test_local_block_adds_paths_and_sets_limits():
    resolved = policy.resolve({
        "extends": ["reins:base"],
        "floor": {"governed_paths": ["services/billing/**"],
                  "max_files": 10, "max_lines": 300},
    })
    assert "services/billing/**" in resolved["governed_paths"]
    assert (resolved["max_files"], resolved["max_lines"]) == (10, 300)


def test_resolution_is_deterministic_and_deduplicated():
    cfg = {"extends": ["reins:auth", "reins:auth"],
           "floor": {"governed_paths": ["**/auth/**"]}}
    paths = policy.resolve(cfg)["governed_paths"]
    assert len(paths) == len(set(paths))
    assert policy.resolve(cfg) == policy.resolve(cfg)


@pytest.mark.parametrize("bad", [
    {"extends": ["reins:nonexistent"]},
    {"extends": ["node"]},
    {"extends": [42]},
])
def test_unknown_presets_raise_rather_than_being_skipped(bad):
    """A silently ignored preset is a control the reader believes is on."""
    with pytest.raises(ValueError):
        policy.resolve(bad)


def test_empty_config_resolves_to_defaults_not_an_error():
    resolved = policy.resolve({})
    assert resolved["governed_paths"] == []
    assert resolved["presets"] == []


# --- the failures this exists to catch --------------------------------

def test_audit_finds_the_ungoverned_auth_service():
    """The grounding instance: `**/auth/**` does not match
    `backend-core/auth-service/`, so the most security-sensitive code in
    the repository was silently taking the cheap lane."""
    cfg = {"floor": {"governed_paths": ["**/auth/**", "**/migrations/**"]}}
    gaps = {g["preset"]: g for g in policy.audit(cfg, MONOREPO)["coverage_gaps"]}
    assert "auth" in gaps
    assert any("auth-service" in e for e in gaps["auth"]["examples"])


def test_audit_reports_presets_worth_adding_and_dropping():
    cfg = {"extends": ["reins:base", "reins:node", "reins:go"]}
    a = policy.audit(cfg, MONOREPO)
    assert "auth" in a["presets_missing"]
    assert "api-contracts" in a["presets_missing"]
    assert a["presets_unnecessary"] == ["go"]      # no go.mod in this repo


def test_dead_patterns_covers_hand_written_rules_only():
    """A preset's `**/secrets/**` matching nothing is the desired state,
    not a defect — only patterns a human wrote are reported."""
    cfg = {"extends": ["reins:base"],
           "floor": {"governed_paths": ["**/Cargo.toml", "web/**"]}}
    dead = policy.audit(cfg, MONOREPO)["dead_patterns"]
    assert dead == ["**/Cargo.toml"]
    assert "**/secrets/**" not in dead


def test_audit_never_mutates_its_inputs():
    cfg = {"extends": ["reins:base"], "floor": {"governed_paths": ["x/**"]}}
    before = repr(cfg)
    policy.audit(cfg, MONOREPO, [{"files": 1, "lines": 1}])
    assert repr(cfg) == before


# --- limits: report fit, never fit blindly ----------------------------

SAMPLES = [{"files": 1, "lines": 20}, {"files": 22, "lines": 900},
           {"files": 6, "lines": 180}, {"files": 81, "lines": 3000},
           {"files": 2, "lines": 40}]


def test_limit_fit_reports_distribution_and_express_share():
    fit = policy.limit_fit(SAMPLES, max_files=3, max_lines=100)
    assert fit["samples"] == 5
    assert fit["express_qualifying"] == 2          # the 1/20 and 2/40 changes
    assert fit["express_share"] == 0.4
    assert fit["files"]["max"] == 81
    assert fit["review_effective_lines"] == [200, 400]


def test_limit_fit_warns_when_the_express_lane_is_inert():
    fit = policy.limit_fit([{"files": 30, "lines": 900}] * 5, 3, 100)
    assert fit["express_share"] == 0.0
    assert any("inert" in n for n in fit["notes"])


def test_limit_fit_warns_when_the_floor_almost_never_triggers():
    fit = policy.limit_fit([{"files": 1, "lines": 5}] * 10, 3, 100)
    assert fit["express_share"] == 1.0
    assert any("close to no floor" in n for n in fit["notes"])


def test_limit_fit_flags_limits_above_the_review_effective_band():
    fit = policy.limit_fit(SAMPLES, max_files=50, max_lines=2000)
    assert any("peer review is most effective" in n for n in fit["notes"])


def test_limit_fit_is_honest_about_having_no_samples():
    fit = policy.limit_fit([], 3, 100)
    assert fit["express_share"] is None
    assert any("cannot be assessed" in n for n in fit["notes"])


def test_proposal_never_widens_the_limits_to_match_the_repo():
    """The decision this module most deliberately does NOT make. A repo
    whose changes are routinely large does not need a higher bar; that
    is what the bar is for. Fitting limits to the observed distribution
    would ratify the very changes the floor exists to catch."""
    big = [{"files": 40, "lines": 2000}] * 20
    proposal = policy.propose(MONOREPO, big)
    assert proposal["floor"]["max_files"] == DEFAULT_MAX_FILES
    assert proposal["floor"]["max_lines"] == DEFAULT_MAX_LINES
    assert proposal["limits"]["express_share"] == 0.0   # stated, not fixed


# --- proposals --------------------------------------------------------

def test_proposal_has_no_dead_patterns_by_construction():
    proposal = policy.propose(MONOREPO, SAMPLES)
    resolved = policy.resolve({"extends": proposal["extends"]})
    hand_written = policy.dead_patterns(
        list(proposal.get("floor", {}).get("governed_paths") or []), MONOREPO)
    assert hand_written == []
    assert resolved["governed_paths"]                    # and it governs things


def test_proposal_explains_every_preset_it_offers():
    proposal = policy.propose(MONOREPO, SAMPLES)
    for ref in proposal["extends"]:
        name = ref[len(policy.PRESET_PREFIX):]
        assert proposal["rationale"][name]               # a stated reason
    assert all(r.startswith(policy.PRESET_PREFIX) for r in proposal["extends"])


def test_proposing_then_auditing_leaves_nothing_to_report():
    """A proposal accepted verbatim should come back clean, or the two
    halves disagree about what good looks like."""
    proposal = policy.propose(MONOREPO, SAMPLES)
    a = policy.audit({"extends": proposal["extends"],
                      "floor": proposal["floor"]}, MONOREPO, SAMPLES)
    assert a["presets_missing"] == []
    assert a["presets_unnecessary"] == []
    assert a["dead_patterns"] == []
    assert a["coverage_gaps"] == []
