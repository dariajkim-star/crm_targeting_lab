"""The official 2x2 quadrant assignment (CAP-5, FR11, AD-12).

THIS MODULE IS THE ONLY PLACE `quadrant_official` IS DECIDED.

The simulator (3-2), the budget-constrained priority (3-3), the sensitivity
sweep (3-4) and the customer mart (4-1) CONSUME the column this produces. None
of them may cut its own threshold - AD-12 exists because a matrix drawn at the
median and a target list cut at the 70th percentile put the same customer in
"Save first" on the dashboard and outside the campaign.

What this module deliberately does not know
-------------------------------------------
Budget, contact cost, retention success rate, expected savings. The four cells
are a statement about WHO, not about what a campaign can afford - AD-9 fixes
the direction `matrix -> simulate -> sensitivity` and a structure guard
enforces it. If a future change needs a budget number here, the design is
wrong, not the guard.

Customer value is CONSUMED, never recomputed (AD-11). This module takes the
value axis as a `Series` argument - the caller passes the persisted output of
`crm.segment.value.customer_value`, and nothing here reaches for the source
column or re-weights it. `value.py`'s own docstring points at this step for the
scaling it declines to do; the scaling happens below, inside the assignment,
and never leaks back into the value definition.

Rank, not magnitude - and the LIMIT of that claim (story AC6)
------------------------------------------------------------
The rule reads the ORDER of `churn_prob`, never its calibrated size: both cuts
are quantiles. The scored artifact is in-sample and uncalibrated (mean 0.1976
against a 0.1607 attrition rate, with the 8th decile off by roughly 20x), and
whether to recalibrate is retro action A2, still undecided.

A STRICTLY increasing transform cannot move any customer across a quantile, so
that class of recalibration leaves every assignment untouched.

THAT IS NOT THE SAME AS "A2 CANNOT AFFECT THIS MODULE". An earlier version of
this docstring claimed exactly that and it is false: isotonic regression - the
most likely calibration choice, and the one already used to MEASURE the
miscalibration - is monotone NON-decreasing and collapses distinct scores onto
shared plateaus. A plateau spanning the cut changes who clears it. Measured:

    risk       [0.1, 0.2, 0.3, 0.4, 0.5]  -> cut 0.4, two customers high
    calibrated [0.0, 0.0, 0.0, 0.0, 1.0]  -> cut 0.0, ALL FIVE high

So the honest contract is: **strictly increasing recalibration is safe here;
plateau-producing recalibration is not.** If A2 lands on isotonic, story 3-1
must be revisited - either by assigning on the raw ranking score and reserving
the calibrated probability for 3-2's expected-savings arithmetic, or by
re-deriving the cuts. `test_matrix.py` pins both directions: invariance under a
strictly increasing transform, and the plateau counter-example.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from crm.config import BOUNDARY_UPPER_INCLUSIVE, QUADRANT_RULE, Quadrant, QuadrantRule

__all__ = [
    "QuadrantAssignment",
    "QuadrantThresholds",
    "assign_quadrant",
    "quadrant_thresholds",
]

_RISK_AXIS = "churn_prob"
_VALUE_AXIS = "customer value"


@dataclasses.dataclass(frozen=True)
class QuadrantThresholds:
    """The cuts actually realised on a given population."""

    risk: float
    value: float


@dataclasses.dataclass(frozen=True)
class QuadrantAssignment:
    """Labels and the cuts that produced them, from ONE computation.

    Why these travel together
    -------------------------
    AD-3 requires the mart to carry both `quadrant_official` and the official
    thresholds (`threshold_official_*`), so a Tableau scenario view can always
    draw the baseline it deviates from. Returning only labels and offering a
    separate `quadrant_thresholds()` call left a hole: story 4-1 could compute
    the labels on the full customer base and the thresholds on a filtered or
    mis-joined subset, and the mart would pair a full-population label column
    with a partial-population cut. Nothing would error and the numbers would
    look reasonable.

    `population_size` is carried for the same reason - 4-1 can assert it
    against the mart row count instead of trusting that no rows were dropped
    between the two.
    """

    labels: pd.Series
    thresholds: QuadrantThresholds
    rule: QuadrantRule
    population_size: int


def _validate_rule(rule: QuadrantRule) -> None:
    """Validate ANY rule reaching the function, not just the config default.

    `crm/config.py` checks `QUADRANT_RULE` at import time, but that check
    cannot see a rule built by `replace()` at a call site - and a sweep
    (story 3-4) does exactly that. Without this, `replace(risk_quantile=0.0)`
    ran happily and emptied one side of the axis, and
    `replace(boundary="lower_exclusive")` produced the standard `>=` result
    while claiming a different rule.
    """
    for name, quantile in (
        ("risk_quantile", rule.risk_quantile),
        ("value_quantile", rule.value_quantile),
    ):
        if not 0.0 < quantile < 1.0:
            raise ValueError(
                f"QuadrantRule.{name} must lie strictly between 0 and 1, got "
                f"{quantile}. A cut at 0 or 1 empties one side of the axis."
            )
    if rule.boundary != BOUNDARY_UPPER_INCLUSIVE:
        raise ValueError(
            f"Unsupported boundary rule '{rule.boundary}'. Only "
            f"'{BOUNDARY_UPPER_INCLUSIVE}' (>=) is implemented - a rule object "
            f"declaring anything else would silently get `>=` anyway, which is "
            f"worse than refusing it."
        )


def _validate_axis(series: pd.Series, axis_name: str) -> None:
    """Reject inputs a quantile would silently accept.

    `Series.quantile` skips NaN, so missing scores yield a threshold computed
    from a SUBSET while the comparison below quietly labels every NaN row as
    low. Infinities are worse: one `inf` drags the cut to `inf`, and an
    all-`inf` axis makes the quantile NaN, every comparison False, and the
    ENTIRE customer base "low risk" behind a RuntimeWarning. That is the defect
    shape this project keeps catching late - plausible output, wrong population.
    """
    if series.empty:
        raise ValueError(
            f"assign_quadrant received an empty {axis_name} axis. An empty "
            f"population has no quantiles, and returning an empty frame would "
            f"let a broken upstream stage look like a customer base of zero."
        )
    if series.isna().any():
        count = int(series.isna().sum())
        raise ValueError(
            f"assign_quadrant received {count} missing value(s) on the "
            f"{axis_name} axis. Quantiles ignore NaN, so the threshold would "
            f"come from a subset while every NaN row was labelled low - fix "
            f"the upstream stage rather than imputing here."
        )
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            f"assign_quadrant received non-finite value(s) on the {axis_name} "
            f"axis. A single infinity drags the quantile to infinity; an "
            f"all-infinite axis makes it NaN and silently labels every "
            f"customer low."
        )
    if axis_name == _RISK_AXIS and ((values < 0.0) | (values > 1.0)).any():
        out_of_range = int(((values < 0.0) | (values > 1.0)).sum())
        raise ValueError(
            f"assign_quadrant received {out_of_range} {axis_name} value(s) "
            f"outside [0, 1]. The axis is a probability by contract; a score "
            f"on some other scale would still produce plausible quadrants."
        )
    # No range check on the value axis on purpose: `customer_value()` returns
    # the RAW measured scale and does not promise non-negativity, so asserting
    # `>= 0` here would encode a contract value.py has not made (AD-11 - the
    # value definition is not this module's to extend).


def _validate_pair(churn_prob: pd.Series, value: pd.Series) -> None:
    if len(churn_prob) != len(value):
        raise ValueError(
            f"assign_quadrant needs one risk score per customer value: got "
            f"{len(churn_prob)} and {len(value)}."
        )
    if not churn_prob.index.equals(value.index):
        raise ValueError(
            "assign_quadrant needs the two axes to share an index. pandas "
            "would ALIGN mismatched labels and fill the gaps with NaN, so a "
            "join done wrong upstream would surface as a plausible-looking "
            "matrix over the wrong customers."
        )
    if not churn_prob.index.is_unique:
        duplicated = churn_prob.index[churn_prob.index.duplicated()].unique()
        raise ValueError(
            f"assign_quadrant received a duplicated customer index "
            f"{duplicated[:5].tolist()}. A fan-out join would otherwise give "
            f"one customer two official quadrants and inflate the population "
            f"the cuts are computed from - both axes sharing the same "
            f"duplication makes it invisible to the index check above."
        )


def quadrant_thresholds(
    churn_prob: pd.Series,
    value: pd.Series,
    *,
    rule: QuadrantRule = QUADRANT_RULE,
) -> QuadrantThresholds:
    """Compute the cuts this population implies under ``rule``.

    The edges are computed HERE, at runtime, and never parked in
    ``crm/config.py`` - config owns the quantile levels (a convention), the
    data owns the edges (AD-1). See ``QuadrantRule`` for the full argument.

    Args:
        churn_prob: Risk score per customer. Only its ORDER is used.
        value: Customer value per customer, the persisted ``customer_value``
            output on its raw scale (AD-11 - not recomputed, not re-weighted).
        rule: The cutting rule. Defaults to the single config constant; a
            sweep passes a modified copy rather than mutating the constant.

    Returns:
        The realised risk and value cuts.

    Raises:
        ValueError: on an empty axis, missing values, mismatched lengths, or
            mismatched indexes.
    """
    _validate_rule(rule)
    _validate_axis(churn_prob, _RISK_AXIS)
    _validate_axis(value, _VALUE_AXIS)
    _validate_pair(churn_prob, value)

    return QuadrantThresholds(
        risk=float(churn_prob.quantile(rule.risk_quantile)),
        value=float(value.quantile(rule.value_quantile)),
    )


def assign_quadrant(
    churn_prob: pd.Series,
    value: pd.Series,
    *,
    rule: QuadrantRule = QUADRANT_RULE,
) -> QuadrantAssignment:
    """Assign every customer exactly one official quadrant.

    A customer sitting exactly ON a threshold goes to the UPPER cell - the
    ``>=`` in ``rule.boundary``, stated as a rule rather than left implicit in
    the operator below.

    Args:
        churn_prob: Risk score per customer, a probability in ``[0, 1]``. Only
            its ORDER is used - see the module docstring for the exact limit of
            that claim under recalibration.
        value: Customer value per customer (AD-11: consumed, not recomputed).
        rule: The cutting rule; defaults to the config constant.

    Returns:
        A :class:`QuadrantAssignment` carrying the labels, the realised cuts
        and the rule from a SINGLE computation, so a consumer cannot pair
        labels with thresholds derived from a different population. Labels are
        the Enum's ASCII members - the Korean display labels are the report
        layer's job.

    Raises:
        ValueError: on an unsupported rule, an empty axis, missing or
            non-finite values, risk outside ``[0, 1]``, mismatched lengths,
            mismatched indexes, or a duplicated customer index.
    """
    thresholds = quadrant_thresholds(churn_prob, value, rule=rule)

    # `>=`: the upper cell owns its edge (AD-12, AC3).
    high_risk = churn_prob >= thresholds.risk
    high_value = value >= thresholds.value

    # Built from the two booleans rather than chained conditions so that all
    # four cells are constructed by the same expression - a relabelling typo
    # cannot hide in a branch that the common case never takes.
    quadrants = pd.Series(Quadrant.ACCEPT_CHURN.value, index=churn_prob.index, dtype=object)
    quadrants[high_risk & high_value] = Quadrant.SAVE_FIRST.value
    quadrants[high_risk & ~high_value] = Quadrant.WATCH.value
    quadrants[~high_risk & high_value] = Quadrant.LOW_COST_KEEP.value

    return QuadrantAssignment(
        labels=quadrants.rename(None),
        thresholds=thresholds,
        rule=rule,
        population_size=len(quadrants),
    )
