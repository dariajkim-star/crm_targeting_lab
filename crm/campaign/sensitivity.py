"""Sensitivity of the campaign conclusion to its assumptions (CAP-7, FR14, 3-4).

This is the END of the campaign chain. The 2x2 (3-1) says WHO, `simulate.py`
(3-2) says what one contact is WORTH, `priority.py` (3-3) says WHO FIRST under a
budget, and this module answers the question a decision-maker actually has to
live with: WHEN DOES THE CONCLUSION FLIP if the two assumptions - the retention
success rate and the cost per contact - are wrong?

The "conclusion" is not the total (measured, D1)
------------------------------------------------
FR14 asks "in which assumption region does the conclusion flip" but does not say
WHICH conclusion. Measured on the real artifact, the total net saving is
positive across the ENTIRE 25-point grid - even the worst corner (rate 0.10,
cost 20.0) sums to +299,034 over the positive customers. Drawing a contour of
the total therefore shows a smooth monotone surface with NO flip region, which
is not "the campaign is unconditionally right" - it is the WRONG LAYER.

Two conclusions actually flip, and this module reports at their layer:

  - the SHARE of the base whose contact clears break-even (`share_positive`),
    which swings from 20.3% to 100% across the grid; and
  - the SIGN of each quadrant's mean saving. `save_first` and `watch` (the
    high-risk cells) are positive in all 25 grid points - robust. `low_cost_keep`
    and `accept_churn` (the low-risk cells) change sign inside the grid -
    fragile: contacting them is a decision the assumptions make, not the data.

Consume, never re-derive (AD-9)
-------------------------------
Every number here comes from RE-CALLING `expected_saving()` with different
`retention_rate` / `cost_per_contact` arguments. The break-even formula
(`P*value = cost/rate`) is NOT re-implemented anywhere; break-even is read off
the SIGN of the function's output. That is why 3-2 made the assumptions
parameters rather than module constants. The quadrant compositions in the
risk_quantile annex likewise CONSUME `assign_quadrant` with a replaced rule -
this module never cuts a quantile of its own (AD-12; a structure guard,
`find_sensitivity_selfcut_violations`, fails the build if it does).

What this module deliberately does not do
-----------------------------------------
No budget, ranking or multiple (priority.py, 3-3). No new quadrant cut, no
`quadrant_official` redefinition or persistence (AD-3: the annex is a SCENARIO,
never official). No re-definition or re-weighting of customer value (AD-11). No
new config file or grid literal - the grids live in `crm/config.py` and arrive
as arguments whose defaults reference them (AD-4). No pipeline stage: this is a
pure function feeding a session report, the official home for these figures is
the 4-1 mart and the 4-3 dashboard (M2).

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from crm.campaign.matrix import assign_quadrant
from crm.campaign.simulate import expected_saving
from crm.config import (
    COST_GRID,
    COST_PER_CONTACT,
    QUADRANT_RULE,
    RETENTION_GRID,
    RETENTION_SUCCESS_RATE,
    Quadrant,
    QuadrantRule,
)

__all__ = [
    "GridCell",
    "QuadrantSensitivity",
    "SensitivityGrid",
    "QuadrantComposition",
    "RiskQuantileAnnex",
    "sweep_sensitivity",
    "quadrant_breakeven_rate",
    "risk_quantile_annex",
]

_VALUE_AXIS = "customer_value"
# Bisection tolerance for locating a break-even rate. Small relative to the
# grid spacing (0.10) so the reported rate is precise to the printed digits;
# not a data value, a numerical convention.
_BREAKEVEN_TOL = 1e-9
# Widest bracket a retention rate can take: (0, 1]. `expected_saving` refuses a
# rate of exactly 0 (the ranking information collapses there), so the low end
# is an epsilon above it rather than 0 itself.
_RATE_BRACKET = (1e-9, 1.0)


@dataclasses.dataclass(frozen=True)
class GridCell:
    """One (rate, cost) point: what the whole base looks like under it.

    `share_positive` is the fraction of customers whose expected saving is
    strictly positive - the "contactable base ratio" that D1 identifies as one
    of the two conclusions that actually move. `distinct_savings` is carried so
    a consumer can SEE that no ties formed (D3), rather than trusting a claim.
    """

    retention_rate: float
    cost_per_contact: float
    share_positive: float
    total_net: float
    total_positive: float
    distinct_savings: int
    population_size: int

    @property
    def ties(self) -> int:
        """How many savings collapsed onto a shared value at this point (D3)."""
        return self.population_size - self.distinct_savings


@dataclasses.dataclass(frozen=True)
class QuadrantSensitivity:
    """A quadrant's verdict across the grid: robust or fragile (D1).

    `cells_positive` counts how many of the grid points give this quadrant a
    positive MEAN saving. `robust` is True only when every grid point agrees on
    the sign - the honest statement of "the assumptions do not change this
    conclusion". A quadrant that is positive in some cells and negative in
    others is FRAGILE: whether to contact it is a decision the assumptions make.
    """

    label: str
    population: int
    per_capita_min: float
    per_capita_max: float
    cells_positive: int
    cells_total: int

    @property
    def robust(self) -> bool:
        """True when the quadrant's sign never flips across the grid."""
        return self.cells_positive == 0 or self.cells_positive == self.cells_total


@dataclasses.dataclass(frozen=True)
class SensitivityGrid:
    """The full 2D sweep, self-describing about its representative point.

    `representative` is the (rate, cost) the rest of the project quotes as its
    headline; it is asserted to sit ON the grid (AD-4, the same invariant
    `crm/config.py` guards at import time) so a reader cannot pair a headline
    number with a curve it does not lie on.
    """

    cells: tuple[GridCell, ...]
    quadrants: tuple[QuadrantSensitivity, ...]
    retention_grid: tuple[float, ...]
    cost_grid: tuple[float, ...]
    representative: tuple[float, float]

    def cell(self, retention_rate: float, cost_per_contact: float) -> GridCell:
        """The grid cell at exactly (rate, cost). Raises if it is not a point."""
        for c in self.cells:
            if c.retention_rate == retention_rate and c.cost_per_contact == cost_per_contact:
                return c
        raise KeyError(
            f"({retention_rate}, {cost_per_contact}) is not a grid point; the "
            f"grid is {self.retention_grid} x {self.cost_grid}."
        )

    def representative_cell(self) -> GridCell:
        """The headline cell - guaranteed present by the constructor check."""
        return self.cell(*self.representative)

    @property
    def fragile_quadrants(self) -> tuple[QuadrantSensitivity, ...]:
        """Quadrants whose sign the assumptions decide (D1)."""
        return tuple(q for q in self.quadrants if not q.robust)

    @property
    def robust_quadrants(self) -> tuple[QuadrantSensitivity, ...]:
        """Quadrants the assumptions never flip (D1)."""
        return tuple(q for q in self.quadrants if q.robust)


@dataclasses.dataclass(frozen=True)
class QuadrantComposition:
    """One risk_quantile scenario: how the four cells are sized under it.

    This is a SCENARIO, not the official assignment (AD-3). `counts` is a tuple
    of (label, size) pairs rather than a dict so the whole dataclass stays
    frozen and hashable, and so the ordering the report prints is fixed.
    """

    risk_quantile: float
    risk_cut: float
    counts: tuple[tuple[str, int], ...]

    def count(self, label: str) -> int:
        for name, size in self.counts:
            if name == label:
                return size
        raise KeyError(f"no quadrant labelled {label!r} in this composition")


@dataclasses.dataclass(frozen=True)
class RiskQuantileAnnex:
    """The 3-1 deferred sweep: how much the QUADRANT DEFINITION moves the result.

    A DIFFERENT KIND of sensitivity from rate/cost - structural, not parametric.
    Moving `risk_quantile` from 0.70 to 0.80 re-sizes the cells (measured:
    save_first 537 -> 348) without touching `expected_saving` at all. This is a
    robustness CHECK on the definition, NOT a re-opening of the official cut:
    `official_quantile` records which scenario is the shipped rule, and NOTHING
    here is written back as `quadrant_official` or into a mart (AD-3). The frame
    handed to Tableau is the 4-1/4-3 job and must not pick this up as official.
    """

    compositions: tuple[QuadrantComposition, ...]
    official_quantile: float
    value_quantile: float

    def composition(self, risk_quantile: float) -> QuadrantComposition:
        for c in self.compositions:
            if c.risk_quantile == risk_quantile:
                return c
        raise KeyError(f"risk_quantile {risk_quantile} not in the annex sweep")


def _quadrant_labels_for(labels: pd.Series, index: pd.Index) -> pd.Series:
    """Align the official quadrant labels to the saving population.

    Raised rather than realigned: `expected_saving` and `assign_quadrant` must
    be computed on the SAME customers in the SAME order, or a per-quadrant mean
    would average one customer's saving under another's label. pandas would
    silently align on the index and fill gaps with NaN, so this refuses a
    mismatch outright.
    """
    if not isinstance(labels, pd.Series):
        raise ValueError(
            f"quadrant labels must be a Series, got {type(labels).__name__}."
        )
    if not labels.index.equals(index):
        raise ValueError(
            "sweep_sensitivity needs the quadrant labels and the saving axes to "
            "share an index. A mismatch means the labels and the money were "
            "computed on different populations - re-run assign_quadrant on the "
            "same joined frame the probability and value come from."
        )
    return labels


def sweep_sensitivity(
    churn_prob_calibrated: pd.Series,
    value: pd.Series,
    quadrant_labels: pd.Series,
    *,
    retention_grid: tuple[float, ...] = RETENTION_GRID,
    cost_grid: tuple[float, ...] = COST_GRID,
    representative: tuple[float, float] = (RETENTION_SUCCESS_RATE, COST_PER_CONTACT),
) -> SensitivityGrid:
    """Sweep `expected_saving` over the rate x cost grid (FR14, AC1, D1).

    The two conclusions this reports - `share_positive` per cell and the SIGN of
    each quadrant's mean - are the layers that actually flip (D1); the total net
    saving does not (it is positive across the whole grid) and is not the
    headline. Every number is produced by re-calling `expected_saving`; the
    break-even formula is never re-derived (AD-9).

    Args:
        churn_prob_calibrated: Calibrated churn probability per customer, the
            `churn_prob_calibrated` column (3-0). Passed straight to
            `expected_saving`, which refuses the raw ranking score by name.
        value: Customer value per customer, the persisted `customer_value`
            output on its raw scale (AD-11 - consumed, never recomputed).
        quadrant_labels: The OFFICIAL quadrant per customer, the `labels` from
            `assign_quadrant` (AD-12 - consumed, never re-cut here). Must share
            the index of the saving axes.
        retention_grid: Retention success rates to sweep. Defaults to the config
            grid; a caller passes a grid, never a re-declared literal (AD-4).
        cost_grid: Contact costs to sweep. Same contract.
        representative: The headline (rate, cost). Must be a point on the grid,
            checked here for the same reason `crm/config.py` checks it at import.

    Returns:
        A :class:`SensitivityGrid` carrying every cell, the per-quadrant verdict,
        and the representative point it is guaranteed to contain.

    Raises:
        ValueError: on an empty grid, a representative point off the grid, or
            quadrant labels that do not share the saving index. Axis-content
            errors (NaN, wrong dtype, mislabelled probability) are raised by
            `expected_saving` itself.
    """
    if not retention_grid or not cost_grid:
        raise ValueError(
            "sweep_sensitivity needs a non-empty retention grid and cost grid; "
            "an empty sweep would return a confident answer about no scenarios."
        )
    rep_rate, rep_cost = representative
    if rep_rate not in retention_grid or rep_cost not in cost_grid:
        raise ValueError(
            f"representative point ({rep_rate}, {rep_cost}) must lie on the grid "
            f"{tuple(retention_grid)} x {tuple(cost_grid)} so the headline "
            f"number sits on the sensitivity curve (AD-4)."
        )

    labels = _quadrant_labels_for(quadrant_labels, churn_prob_calibrated.index)
    population = len(churn_prob_calibrated)

    # Compute every cell's saving ONCE and keep it, so the per-quadrant pass
    # below reuses the same Series rather than re-calling expected_saving a
    # second time per cell.
    savings: dict[tuple[float, float], pd.Series] = {}
    cells: list[GridCell] = []
    for rate in retention_grid:
        for cost in cost_grid:
            saving = expected_saving(
                churn_prob_calibrated,
                value,
                retention_rate=rate,
                cost_per_contact=cost,
            )
            savings[(rate, cost)] = saving
            positive = saving > 0.0
            cells.append(
                GridCell(
                    retention_rate=rate,
                    cost_per_contact=cost,
                    share_positive=float(positive.mean()),
                    total_net=float(saving.sum()),
                    total_positive=float(saving[positive].sum()),
                    distinct_savings=int(saving.nunique()),
                    population_size=population,
                )
            )

    quadrants: list[QuadrantSensitivity] = []
    for label in labels.drop_duplicates().sort_values():
        mask = labels == label
        count = int(mask.sum())
        means = [float(saving[mask].mean()) for saving in savings.values()]
        cells_positive = sum(1 for m in means if m > 0.0)
        quadrants.append(
            QuadrantSensitivity(
                label=str(label),
                population=count,
                per_capita_min=min(means),
                per_capita_max=max(means),
                cells_positive=cells_positive,
                cells_total=len(means),
            )
        )

    return SensitivityGrid(
        cells=tuple(cells),
        quadrants=tuple(quadrants),
        retention_grid=tuple(retention_grid),
        cost_grid=tuple(cost_grid),
        representative=(rep_rate, rep_cost),
    )


def quadrant_breakeven_rate(
    churn_prob_calibrated: pd.Series,
    value: pd.Series,
    quadrant_labels: pd.Series,
    label: str,
    *,
    cost_per_contact: float,
    bracket: tuple[float, float] = _RATE_BRACKET,
    tol: float = _BREAKEVEN_TOL,
) -> float | None:
    """Retention rate at which a quadrant's MEAN saving crosses zero (AC3, T2).

    Break-even is a CONTINUOUS hyperbola in (rate, cost), not a grid point
    (함정 5): the rate that flips a fragile quadrant almost never lands on the
    coarse grid. This locates it by BISECTION on the SIGN of `expected_saving`
    (AD-9 - the formula is never re-derived), which is valid because the mean is
    monotone increasing in the rate for non-negative value.

    Args:
        churn_prob_calibrated: Calibrated probability per customer.
        value: Customer value per customer (AD-11 - consumed).
        quadrant_labels: Official quadrant labels sharing the saving index.
        label: Which quadrant to locate break-even for.
        cost_per_contact: The cost to hold fixed while the rate is varied.
        bracket: (low, high) retention rates to search between. `expected_saving`
            refuses a rate of exactly 0, so `low` is an epsilon above it.
        tol: Half-width at which the bisection stops.

    Returns:
        The retention rate at which the quadrant mean is zero, or ``None`` when
        the quadrant does not change sign anywhere in the bracket (robust at
        this cost - there is no break-even to report).

    Raises:
        ValueError: for a label absent from the population, or the axis-content
            errors `expected_saving` raises.
    """
    labels = _quadrant_labels_for(quadrant_labels, churn_prob_calibrated.index)
    mask = labels == label
    if not bool(mask.any()):
        raise ValueError(
            f"no customers are labelled {label!r}; there is no quadrant mean to "
            f"find a break-even for."
        )

    # Subset to the quadrant ONCE, then sweep the rate on just those customers.
    # `expected_saving` over the whole population per bisection step would
    # compute ~10k savings only to average a few hundred - the mean is a
    # property of this quadrant alone. Boolean indexing keeps the Series name
    # and a shared index, so `expected_saving`'s pairing checks still hold.
    prob_q = churn_prob_calibrated[mask]
    value_q = value[mask]

    def mean_at(rate: float) -> float:
        saving = expected_saving(
            prob_q,
            value_q,
            retention_rate=rate,
            cost_per_contact=cost_per_contact,
        )
        return float(saving.mean())

    lo, hi = bracket
    mean_lo, mean_hi = mean_at(lo), mean_at(hi)
    # No sign change in the bracket => no break-even to report. Robust quadrants
    # (always positive) and never-worth-it ones (always negative) land here.
    if (mean_lo > 0.0) == (mean_hi > 0.0):
        return None

    # Monotone increasing in the rate, so the root is where the mean turns
    # from negative to positive. Standard bisection on the sign.
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if mean_at(mid) > 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def risk_quantile_annex(
    churn_score: pd.Series,
    value: pd.Series,
    *,
    risk_quantiles: tuple[float, ...] = (0.70, 0.75, 0.80),
    base_rule: QuadrantRule = QUADRANT_RULE,
) -> RiskQuantileAnnex:
    """Sweep the QUADRANT DEFINITION, not the money (AC7, D2 - the 3-1 deferral).

    Physically separate from the FR14 rate/cost contour (John's condition): a
    different axis (structural, not parametric) that must not be drawn on the
    same plot. Each scenario CONSUMES `assign_quadrant` with a rule whose
    `risk_quantile` is replaced (AD-12 - no cut is computed here), and NOTHING is
    written back as official or into a mart (AD-3). The framing is "does the
    definition change the conclusion", answered honestly: measured, it moves the
    cell sizes MORE than rate/cost do (save_first 537 -> 348 across 0.70->0.80).

    Args:
        churn_score: Raw out-of-fold risk score per customer (3-0). Only its
            ORDER is used - `assign_quadrant` cuts it, this function does not.
        value: Customer value per customer (AD-11 - consumed).
        risk_quantiles: The risk cut levels to sweep. Defaults bracket the
            shipped 0.75.
        base_rule: The rule whose `risk_quantile` is replaced per scenario;
            defaults to the config constant. Its `value_quantile` and boundary
            are held fixed so only the risk definition varies.

    Returns:
        A :class:`RiskQuantileAnnex` of one scenario per quantile, tagged with
        which one is the official rule. Every scenario is a SCENARIO (AD-3).

    Raises:
        ValueError: on an empty quantile sweep, or the axis errors
            `assign_quadrant` raises.
    """
    if not risk_quantiles:
        raise ValueError(
            "risk_quantile_annex needs at least one quantile to sweep; an empty "
            "sweep would answer nothing about the definition's robustness."
        )

    compositions: list[QuadrantComposition] = []
    for q in risk_quantiles:
        assignment = assign_quadrant(churn_score, value, rule=base_rule.replace(risk_quantile=q))
        counts = assignment.labels.value_counts()
        # Count over ALL four official cells, defaulting absent ones to 0. An
        # extreme quantile can empty a cell (e.g. risk_quantile 0.99 leaves no
        # `save_first`), and `value_counts` simply drops the missing label -
        # which used to make `QuadrantComposition.count("save_first")` raise
        # KeyError on a caller-supplied sweep. Every scenario now reports the
        # full four-cell composition, and a 0 is a real answer, not a gap.
        composition_counts = tuple(
            (cell.value, int(counts.get(cell.value, 0))) for cell in Quadrant
        )
        compositions.append(
            QuadrantComposition(
                risk_quantile=q,
                risk_cut=assignment.thresholds.risk,
                counts=composition_counts,
            )
        )

    return RiskQuantileAnnex(
        compositions=tuple(compositions),
        official_quantile=base_rule.risk_quantile,
        value_quantile=base_rule.value_quantile,
    )
