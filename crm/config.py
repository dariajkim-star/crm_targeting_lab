"""Single source of truth for configuration (AD-4).

This is the ONLY configuration file in the project. No YAML / TOML / JSON / .env
runtime config is introduced anywhere (a guard test enforces this).

Two hard rules govern what may live here:

1. AD-4 - every calculation function takes its parameters as arguments whose
   DEFAULTS reference these constants. Never re-declare or hardcode a literal
   at a call site, and never introduce a second config file.
2. AD-1 - no value derived from data may appear here. Quantile edges, means,
   category encodings, fitted thresholds: all forbidden. A value computed from
   one dataset lane and parked here would silently leak into the other lane.
   Every constant therefore carries a `# source:` comment stating its origin.

Encoding note (P1 lesson: cp949 console mishaps on Windows): everything the
RUNTIME parses - names, values, messages - stays ASCII. Provenance comments
(`# source: ...`) use the Korean tags the story AC mandates; the file is UTF-8
and every tool in this repo reads it with an explicit encoding.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import NamedTuple

# --- Reproducibility (AD-7) --------------------------------------------------
# Every stochastic operation must receive this explicitly: K-means
# (random_state + n_init), XGBoost (random_state + n_jobs=1 + fixed tree_method),
# data splits, SHAP background sampling, pymc-marketing (random_seed/chains/
# draws/tune). Omitting the seed argument is a violation, not an oversight.
RANDOM_SEED: int = 42  # source: 규약 (arbitrary but fixed)

# --- Canonical paths ---------------------------------------------------------
# crm/config.py -> project root is one level up.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent  # source: 경로규약
DATA_DIR: Path = PROJECT_ROOT / "data"  # source: 경로규약 (gitignored)
MODELS_DIR: Path = PROJECT_ROOT / "models"  # source: 경로규약 (gitignored)
MARTS_DIR: Path = PROJECT_ROOT / "marts"  # source: 경로규약 (committed; AD-2)

# --- Feature engineering conventions -----------------------------------------
# RFM quantile-score bucket count. A convention, NOT a value derived from data:
# the number 5 is the classic RFM quintile choice and is chosen a priori, so it
# is allowed here (AD-1 forbids only DATA-DERIVED constants). The bucket EDGES
# are computed at runtime from the BankChurners frame and never parked here.
RFM_QUANTILES: int = 5  # source: 규약 (classic RFM quintile convention)

# K-means segment count. A modelling hyperparameter chosen by the analyst from
# the elbow/silhouette curves in story 1-4 (NOT a fitted threshold): inertia's
# marginal gain flattens after k=4 (the elbow), and while k=2 scores the highest
# silhouette it only splits high/low value - too coarse for the downstream 2x2
# and the 1-5 personas. k=4 balances separation and actionability. Derived from
# the BankChurners lane only and used only there (AD-1: no cross-lane reuse).
SEGMENT_K: int = 4  # source: 1-4 elbow/silhouette on BankChurners

# --- Churn model conventions (story 1-6a) ------------------------------------
# Cross-validation fold count for the churn PR-AUC comparison. A convention, not
# a value derived from data.
CHURN_CV_FOLDS: int = 5  # source: 규약 (standard 5-fold)
# XGBoost tree method, PINNED for determinism (AD-7): the histogram method is
# reproducible when n_jobs=1 and random_state are also fixed. Not a data value.
CHURN_TREE_METHOD: str = "hist"  # source: 규약 (deterministic with n_jobs=1)

# --- SHAP explanation conventions (story 1-7) --------------------------------
# Background sample size for the interventional TreeExplainer. A cost/precision
# convention, NOT a value read off the data: the explainer is O(background x
# rows), and a few hundred reference rows settle the driver RANKING this project
# reports. Sampled with RANDOM_SEED (AD-7).
SHAP_BACKGROUND_SIZE: int = 200  # source: 규약 (cost/precision trade-off)
# How many drivers a per-segment table reports. The epic asks for top5.
DRIVER_TOP_N: int = 5  # source: 규약 (epic 1.7 AC: 요인 top5)

# --- Targeting matrix: the 2x2 decision rule (story 3-1, AD-12) --------------
# ONE rule, declared once. The simulator (3-2) and the sensitivity sweep (3-4)
# CONSUME `quadrant_official`; neither may cut its own threshold. AD-12 exists
# because a 2x2 drawn at the median and a target list cut at the 70th
# percentile put the same customer in "Save first" on the dashboard and outside
# the campaign - the most visible contradiction a portfolio can ship.


class Quadrant(str, Enum):
    """The four official cells (AD-12: an Enum, never a free string).

    VALUES ARE ASCII ON PURPOSE. The Korean display labels this project reports
    ("Save 우선" / "관망" / "저비용 유지" / "이탈 수용") belong to the report and
    dashboard layer, not to anything the runtime parses - the module docstring's
    encoding rule applies to Enum values too (P1 cp949 console lesson).

    Cell meanings (risk axis first, then value axis):
      SAVE_FIRST     high risk, high value  - worth spending to keep
      WATCH          high risk, low value   - likely to leave, cheap to lose
      LOW_COST_KEEP  low risk,  high value  - valuable and not going anywhere
      ACCEPT_CHURN   low risk,  low value   - no action warranted
    """

    SAVE_FIRST = "save_first"
    WATCH = "watch"
    LOW_COST_KEEP = "low_cost_keep"
    ACCEPT_CHURN = "accept_churn"


class QuadrantRule(NamedTuple):
    """How the two axes are cut. A METHOD, not a pair of measured edges.

    Why NamedTuple and not @dataclass (an incidental constraint, not a rule)
    -----------------------------------------------------------------------
    The AD-4 guard test executes this module's source under a synthetic module
    name absent from `sys.modules`, to prove the import-time grid check really
    bites. Building a dataclass under those conditions raises AttributeError:
    `dataclasses` resolves each field annotation to check for ClassVar/InitVar
    by looking the class's module up in `sys.modules`, and gets None. Measured
    while writing this story. NamedTuple reads `__annotations__` directly and
    is unaffected, and is a good fit here anyway - immutable, tiny, tuple-shaped.

    This is a property of how that ONE test loads the file, not an
    architectural prohibition. Do not read it as "config may never hold a
    dataclass": the guard could register the synthetic module first
    (`sys.modules[name] = types.ModuleType(name)` around the `exec`) and the
    constraint disappears. Noted so a later story reaches for the right fix
    rather than rediscovering the crash.

    AD-1 vs AD-12, and why this holds only quantile LEVELS
    -----------------------------------------------------
    AD-12 says the threshold "방식·값" live here. AD-1 forbids data-derived
    values here. Parking `risk_threshold = 0.1607` would satisfy the first and
    violate the second - 0.1607 is read off the label column.

    Story 1-3 already settled this shape for RFM: config holds the quantile
    COUNT (`RFM_QUANTILES = 5`, an a-priori convention), the runtime computes
    the edges, and the report records what they came out to be. The same split
    applies here. The realised cuts are returned by `quadrant_thresholds()` and
    travel to the mart as `threshold_official_*` columns (AD-3), never back
    into this file.

    Why 0.75 on risk and 0.50 on value (the asymmetry is deliberate)
    ---------------------------------------------------------------
    The value axis is split at its median, the textbook 2x2 cut, and
    `customer_value` is spread evenly enough for the median to mean something.

    The risk axis is not. `risk_quantile = 0.75` is a POLICY ASSUMPTION - "the
    top quarter are the high-risk candidates" - and NOT a value shown to be
    optimal. Two things support it and neither proves it:

      - a median cut puts HALF the base in the upper cells, which is useless
        for prioritising a campaign, and the resulting group is 32% attriters
        against 64% at 0.75 (in-sample, `quadrant-report-3-1.md`);
      - recall of actual attriters stays essentially total from 0.50 through
        0.80 and only collapses past it (0.9951 at 0.80, 0.6177 at 0.90).

    Measured honestly, 0.80 buys higher precision (0.799 vs 0.642) at nearly
    the same recall, so 0.75 is a defensible point in a band rather than the
    best point in it. Story 3-4 should sweep this axis alongside success rate
    and cost; until it does, treat the quadrant counts as one scenario.

    Note the argument above is deliberately RANK-based. An earlier version
    justified the choice by reading 0.0051 as "a 0.5% chance of leaving" - which
    contradicts this project's own position that the uncalibrated score's
    magnitude means little. The evidence used here is the realised composition
    of the resulting groups, which survives any strictly monotone rescaling.

    Like `SEGMENT_K`, the number is an analyst's choice informed by the data,
    not a fitted statistic - and the cut it produces (0.12684 on the current
    artifact) is computed at runtime and reported, never parked here.

    Boundary
    --------
    `>=` sends a customer sitting exactly on a threshold to the UPPER cell
    (AC3). Stated here rather than left to the comparison operator in the
    implementation, because "which side does the edge belong to" is a rule, not
    a coding detail.
    """

    risk_quantile: float
    value_quantile: float
    boundary: str

    def replace(self, **changes: float | str) -> "QuadrantRule":
        """Return a copy with fields overridden (used by sweeps and tests).

        A sweep varies the rule by passing a NEW rule object into the function,
        never by mutating this module's constant (AD-4: config is read, not
        rewritten at runtime). Tuples are immutable, so an accidental in-place
        edit raises rather than silently redefining the official rule.

        A public alias for `_replace`: the underscore marks it as part of the
        NamedTuple machinery, not as private, and call sites should not have to
        look that up.
        """
        return self._replace(**changes)


# The upper cell owns its edge. Declared as a constant so the guard below and
# the docstring above refer to the same token.
BOUNDARY_UPPER_INCLUSIVE: str = "upper_inclusive"  # source: 규약 (AD-12 `>=`)

# source: 규약 (a-priori quantile levels; realised cuts are runtime + reported)
QUADRANT_RULE: QuadrantRule = QuadrantRule(
    risk_quantile=0.75,
    value_quantile=0.50,
    boundary=BOUNDARY_UPPER_INCLUSIVE,
)

# --- Campaign policy assumptions (NFR1: assumptions, not measurements) -------
# These are NOT estimated from data. They are stated assumptions, and every
# artifact that uses them must label them as such. Robustness is CAP-7's job
# (story 3-4), which sweeps the grids below.

# Retention success rate: the share of contacted at-risk customers who stay.
# source: 정책가정 (industry-conventional conservative value; SPEC Assumptions)
RETENTION_SUCCESS_RATE: float = 0.30
# source: 정책가정 (sensitivity sweep range for story 3-4)
RETENTION_GRID: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40, 0.50)

# Cost of one retention contact. UNITLESS on purpose: BankChurners carries no
# currency unit, so attaching one would fabricate information (NFR3 currency
# discipline; P1 3-4 shipped a currency mix-up by doing exactly that).
# source: 정책가정 (assumed contact cost, unitless)
COST_PER_CONTACT: float = 5.0
# source: 정책가정 (sensitivity sweep range for story 3-4)
COST_GRID: tuple[float, ...] = (1.0, 2.5, 5.0, 10.0, 20.0)


def ensure_output_dirs() -> None:
    """Create gitignored output directories if missing.

    ``data/`` and ``models/`` are gitignored, so a fresh clone does not have
    them. Pipeline stages call this before writing. Deliberately NOT executed at
    import time - importing a config module should not touch the filesystem.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


# --- Representative-value guards (AD-4) --------------------------------------
# Run at import time so a violation cannot reach runtime. Without these, the
# simulator (3-2) could report a headline number that does not sit anywhere on
# the sensitivity curve (3-4) - P1 shipped exactly that class of defect when a
# cutoff value drifted between two call sites.
# Explicit `raise` rather than `assert`: `python -O` strips asserts, and a
# guard that disappears under an interpreter flag is not a guard.
if RETENTION_SUCCESS_RATE not in RETENTION_GRID:
    raise ValueError(
        "AD-4: RETENTION_SUCCESS_RATE must be a point on RETENTION_GRID so the "
        "simulator's headline result lies on the sensitivity curve."
    )
if COST_PER_CONTACT not in COST_GRID:
    raise ValueError(
        "AD-4: COST_PER_CONTACT must be a point on COST_GRID so the simulator's "
        "headline result lies on the sensitivity curve."
    )
# A quantile outside (0, 1) is not a stricter rule, it is an empty or total
# quadrant - and it would surface as a confusing pandas error deep inside the
# assignment rather than here, where the rule is declared.
for _name, _q in (
    ("risk_quantile", QUADRANT_RULE.risk_quantile),
    ("value_quantile", QUADRANT_RULE.value_quantile),
):
    if not 0.0 < _q < 1.0:
        raise ValueError(
            f"AD-12: QUADRANT_RULE.{_name} must lie strictly between 0 and 1, "
            f"got {_q}. A cut at 0 or 1 empties one side of the axis."
        )
if QUADRANT_RULE.boundary != BOUNDARY_UPPER_INCLUSIVE:
    raise ValueError(
        "AD-12: the only supported boundary rule is "
        f"'{BOUNDARY_UPPER_INCLUSIVE}' (>=). A second convention would let the "
        "2x2 and the target list disagree about the customer on the edge."
    )
