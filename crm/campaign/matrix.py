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

Rank, not magnitude (story AC6)
-------------------------------
The rule reads the ORDER of `churn_prob`, never its calibrated size: both cuts
are quantiles. That is not a stylistic choice - the scored artifact is
in-sample and uncalibrated (mean 0.1976 against a 0.1607 attrition rate, with
the 8th decile off by roughly 20x), and the open question of whether to
recalibrate is retro action A2, still undecided. Because a strictly increasing
transform of the scores cannot move any customer across a quantile, A2's
outcome cannot change a single assignment here. `test_matrix.py` pins that
property mechanically.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import dataclasses

import pandas as pd

from crm.config import QUADRANT_RULE, Quadrant, QuadrantRule

__all__ = ["QuadrantThresholds", "assign_quadrant", "quadrant_thresholds"]

_RISK_AXIS = "churn_prob"
_VALUE_AXIS = "customer value"


@dataclasses.dataclass(frozen=True)
class QuadrantThresholds:
    """The cuts actually realised on a given population.

    Returned rather than merely applied because AD-3 requires the mart to carry
    the official thresholds as `threshold_official_*` columns, so a Tableau
    scenario view can always draw the baseline it is deviating from. Story 4-1
    reads these; this module does not write anything.
    """

    risk: float
    value: float


def _validate_axis(series: pd.Series, axis_name: str) -> None:
    """Reject inputs a quantile would silently accept.

    `Series.quantile` skips NaN, so a frame with missing scores yields a
    threshold computed from a SUBSET of the population while the comparison
    below quietly labels every NaN row as low-risk. That is the shape of defect
    this project has repeatedly caught late (1-1a guard bugs, 1-7 duplicate
    feature): plausible output, wrong population.
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
) -> pd.Series:
    """Assign every customer exactly one official quadrant.

    A customer sitting exactly ON a threshold goes to the UPPER cell - the
    ``>=`` in ``rule.boundary``, stated as a rule rather than left implicit in
    the operator below.

    Args:
        churn_prob: Risk score per customer. Only its ORDER is used (AC6).
        value: Customer value per customer (AD-11: consumed, not recomputed).
        rule: The cutting rule; defaults to the config constant.

    Returns:
        ``Series[str]`` of :class:`~crm.config.Quadrant` values, indexed exactly
        like the inputs. Values are the Enum's ASCII members - the Korean
        display labels are the report layer's job.

    Raises:
        ValueError: on an empty axis, missing values, mismatched lengths, or
            mismatched indexes.
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

    return quadrants.rename(None)
