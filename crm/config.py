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

from pathlib import Path

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
