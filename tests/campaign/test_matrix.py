"""Behavioural tests for the official 2x2 quadrant assignment (story 3-1).

Why these assertions and not others
-----------------------------------
The tautology to avoid is re-deriving the same comparison the implementation
makes (``churn >= churn.quantile(0.75)``) and asserting the two agree. That
passes for any consistent wrongness - a flipped boundary, swapped axes, or a
mislabelled cell - because the test copies the bug (P1 2-2 sign-flip lesson).

So each test names a PROPERTY that AD-12 / the story ACs require and that a
plausible wrong implementation breaks:

  - EXHAUSTIVE and EXCLUSIVE: every row lands in exactly one of the four
    labels, so no customer is silently dropped or double-counted (AC1)
  - MONOTONE in each axis independently: raising a customer's risk can never
    move them to a lower-risk quadrant, and likewise for value. This is the
    probe that catches swapped axes - a swap breaks monotonicity in both.
  - BOUNDARY: a customer sitting exactly on the threshold goes to the UPPER
    quadrant (AC3). The `>` vs `>=` mutation dies here and only here.
  - RANK-ONLY: a strictly increasing transform of the risk scores leaves every
    assignment unchanged. This is the mechanical proof of AC6 - the rule reads
    ORDER, never the calibrated magnitude, so the unresolved calibration debt
    (retro action A2) cannot reach this story.
  - LABELS come from the Enum, never free strings (AC1)
  - FAIL-FAST on empty input, NaN, and misaligned indexes (1-6a/1-6b/1-7
    discipline: no quiet tolerance)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.campaign.matrix import assign_quadrant, quadrant_thresholds
from crm.config import QUADRANT_RULE, Quadrant


def _series(values: list[float], name: str, index: list[int] | None = None) -> pd.Series:
    s = pd.Series(values, dtype=float, name=name)
    if index is not None:
        s.index = pd.Index(index)
    return s


def _paired(risk: list[float], value: list[float]) -> tuple[pd.Series, pd.Series]:
    return _series(risk, "churn_prob"), _series(value, "value")


# A spread wide enough that the 0.75 / 0.50 quantiles fall BETWEEN distinct
# values, so no row sits accidentally on an edge.
#
# The value axis is deliberately NOT co-monotone with risk. An ascending-value
# fixture makes the two axes perfectly correlated, and the high-risk/low-value
# cell (WATCH) becomes unreachable - the suite would then "pass" while never
# exercising a quarter of the rule. Caught by
# `test_all_four_quadrants_are_reachable`.
_RISK = [0.01, 0.02, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80]
_VALUE = [100.0, 800.0, 200.0, 700.0, 300.0, 600.0, 150.0, 900.0]

# Boundary fixtures use n=5 on purpose: with linear interpolation the 0.75
# quantile sits at position 0.75*(5-1) = 3 and the 0.50 quantile at position 2 -
# both land EXACTLY on a data point. That gives a customer who is genuinely on
# the threshold without having to append a row (appending moves the quantile,
# which is what made an earlier version of this test chase its own tail).
_EDGE_RISK = [0.1, 0.2, 0.3, 0.4, 0.5]
_EDGE_VALUE = [10.0, 20.0, 30.0, 40.0, 50.0]


# --- AC1: exhaustive, exclusive, Enum-valued ---------------------------------


def test_every_row_receives_exactly_one_known_label() -> None:
    risk, value = _paired(_RISK, _VALUE)

    result = assign_quadrant(risk, value)

    assert len(result) == len(risk)
    assert result.index.equals(risk.index)
    assert set(result.unique()) <= {q.value for q in Quadrant}
    assert result.notna().all()


def test_labels_are_enum_values_not_free_strings() -> None:
    """A refactor that hand-types 'save_first' somewhere must not drift."""
    risk, value = _paired(_RISK, _VALUE)

    result = assign_quadrant(risk, value)

    # Enum membership, not string equality: a typo'd literal fails to construct.
    for label in result.unique():
        assert Quadrant(label) in Quadrant


def test_all_four_quadrants_are_reachable() -> None:
    """A rule that can never emit one cell would pass the 'exactly one' test."""
    risk, value = _paired(_RISK, _VALUE)

    result = assign_quadrant(risk, value)

    assert set(result.unique()) == {q.value for q in Quadrant}


# --- AC1/AC2: monotonicity - the probe that kills axis swaps -----------------


def test_raising_risk_never_moves_a_customer_to_a_lower_risk_quadrant() -> None:
    risk, value = _paired(_RISK, _VALUE)
    baseline = assign_quadrant(risk, value)

    # Lift the lowest-risk customer above the risk threshold, leaving the
    # thresholds themselves fixed by holding the rest of the distribution.
    lifted = risk.copy()
    lifted.iloc[0] = risk.max() * 10

    result = assign_quadrant(lifted, value)

    high_risk = {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}
    assert baseline.iloc[0] not in high_risk
    assert result.iloc[0] in high_risk


def test_raising_value_never_moves_a_customer_to_a_lower_value_quadrant() -> None:
    risk, value = _paired(_RISK, _VALUE)
    baseline = assign_quadrant(risk, value)

    lifted = value.copy()
    lifted.iloc[0] = value.max() * 10

    result = assign_quadrant(risk, lifted)

    high_value = {Quadrant.SAVE_FIRST.value, Quadrant.LOW_COST_KEEP.value}
    assert baseline.iloc[0] not in high_value
    assert result.iloc[0] in high_value


# --- AC3: boundary belongs to the UPPER quadrant -----------------------------


def test_the_customer_sitting_exactly_on_both_thresholds_goes_upper() -> None:
    """The `>` vs `>=` mutation dies here and only here.

    With n=5 the cuts land exactly on data points: risk q0.75 == 0.4 (index 3)
    and value q0.50 == 30.0 (index 2). Index 3 therefore sits ON the risk cut
    and ABOVE the value cut - under `>=` it is SAVE_FIRST, under `>` it would
    drop to LOW_COST_KEEP.
    """
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)

    thresholds = quadrant_thresholds(risk, value)
    assert thresholds.risk == pytest.approx(0.4)
    assert thresholds.value == pytest.approx(30.0)

    result = assign_quadrant(risk, value)

    assert risk.iloc[3] == thresholds.risk  # genuinely on the edge
    assert result.iloc[3] == Quadrant.SAVE_FIRST.value


def test_the_customer_exactly_on_the_value_cut_counts_as_high_value() -> None:
    """Same edge rule on the other axis (index 2 sits exactly on 30.0)."""
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)

    thresholds = quadrant_thresholds(risk, value)
    result = assign_quadrant(risk, value)

    assert value.iloc[2] == thresholds.value
    assert result.iloc[2] == Quadrant.LOW_COST_KEEP.value


def test_the_customer_immediately_below_the_cut_stays_low_risk() -> None:
    """Companion to the boundary test: `>=` must not swallow everything.

    Note what does NOT work here: nudging the on-edge customer downward. At
    n=5 that customer IS the order statistic the 0.75 quantile points at, so
    lowering their score lowers the cut by the same amount and they stay on the
    edge forever. The honest probe is a DIFFERENT customer who sits strictly
    below the cut.
    """
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)

    thresholds = quadrant_thresholds(risk, value)
    result = assign_quadrant(risk, value)

    assert risk.iloc[2] < thresholds.risk
    assert result.iloc[2] not in {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}


def test_the_cut_separates_neighbouring_customers() -> None:
    """On the n=8 fixture the cut falls strictly BETWEEN two order statistics.

    The pair straddling it must land on opposite sides - a rule that collapsed
    every row into one cell would still satisfy the exhaustiveness test.
    """
    risk, value = _paired(_RISK, _VALUE)

    thresholds = quadrant_thresholds(risk, value)
    result = assign_quadrant(risk, value)

    high_risk = {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}
    assert risk.iloc[5] < thresholds.risk < risk.iloc[6]
    assert result.iloc[5] not in high_risk
    assert result.iloc[6] in high_risk


# --- AC6: rank-only. The mechanical proof that A2 cannot reach this story ----


def test_a_strictly_increasing_transform_of_risk_changes_nothing() -> None:
    """Recalibrating the probabilities must not move a single customer.

    If this ever fails, the rule started reading the MAGNITUDE of churn_prob
    and the unresolved calibration debt (retro A2) has entered story 3-1.
    """
    risk, value = _paired(_RISK, _VALUE)
    baseline = assign_quadrant(risk, value)

    # Monotone but strongly non-linear - exactly the shape of the measured
    # miscalibration (fine at the extremes, distorted in the middle).
    recalibrated = risk**3 / (risk**3 + (1 - risk) ** 3)

    result = assign_quadrant(recalibrated, value)

    pd.testing.assert_series_equal(result, baseline)


# --- Hardcoded oracle --------------------------------------------------------


def test_hardcoded_oracle_four_customers() -> None:
    """Thresholds computed by hand, independent of the implementation.

    risk  = [0.1, 0.2, 0.3, 0.4] -> q0.75 by linear interpolation = 0.325
    value = [10, 20, 30, 40]     -> q0.50 by linear interpolation = 25.0

    customer 0: 0.1 <  0.325, 10 < 25.0 -> accept_churn
    customer 1: 0.2 <  0.325, 20 < 25.0 -> accept_churn
    customer 2: 0.3 <  0.325, 30 >= 25.0 -> low_cost_keep
    customer 3: 0.4 >= 0.325, 40 >= 25.0 -> save_first
    """
    risk, value = _paired([0.1, 0.2, 0.3, 0.4], [10.0, 20.0, 30.0, 40.0])

    thresholds = quadrant_thresholds(risk, value)
    assert thresholds.risk == pytest.approx(0.325)
    assert thresholds.value == pytest.approx(25.0)

    result = assign_quadrant(risk, value)

    assert list(result) == [
        Quadrant.ACCEPT_CHURN.value,
        Quadrant.ACCEPT_CHURN.value,
        Quadrant.LOW_COST_KEEP.value,
        Quadrant.SAVE_FIRST.value,
    ]


def test_watch_cell_is_high_risk_and_low_value() -> None:
    """Pins the WATCH label to its cell - a relabelling mutation dies here."""
    risk, value = _paired([0.1, 0.2, 0.3, 0.4], [40.0, 30.0, 20.0, 10.0])

    result = assign_quadrant(risk, value)

    # customer 3: risk 0.4 >= 0.325 (high), value 10 < 25.0 (low)
    assert result.iloc[3] == Quadrant.WATCH.value


# --- AD-12: the rule comes from config, and only from config -----------------


def test_thresholds_follow_the_configured_quantiles() -> None:
    """Changing the rule changes the cut - the rule is not hardcoded inside."""
    risk, value = _paired(_RISK, _VALUE)

    default = quadrant_thresholds(risk, value)
    stricter = quadrant_thresholds(
        risk, value, rule=QUADRANT_RULE.replace(risk_quantile=0.90)
    )

    assert stricter.risk > default.risk
    assert stricter.value == default.value


def test_rule_defaults_to_the_config_constant() -> None:
    risk, value = _paired(_RISK, _VALUE)

    explicit = quadrant_thresholds(risk, value, rule=QUADRANT_RULE)
    implicit = quadrant_thresholds(risk, value)

    assert explicit == implicit


# --- Fail-fast: no quiet tolerance -------------------------------------------


def test_empty_input_raises_rather_than_returning_an_empty_frame() -> None:
    empty_risk = _series([], "churn_prob")
    empty_value = _series([], "value")

    with pytest.raises(ValueError, match="empty"):
        assign_quadrant(empty_risk, empty_value)


def test_nan_in_risk_raises_and_names_the_axis() -> None:
    risk, value = _paired(_RISK, _VALUE)
    risk.iloc[2] = float("nan")

    with pytest.raises(ValueError, match="churn_prob"):
        assign_quadrant(risk, value)


def test_nan_in_value_raises_and_names_the_axis() -> None:
    risk, value = _paired(_RISK, _VALUE)
    value.iloc[2] = float("nan")

    with pytest.raises(ValueError, match="customer value"):
        assign_quadrant(risk, value)


def test_misaligned_indexes_raise_rather_than_aligning_silently() -> None:
    """pandas would align on the index and fill the gaps with NaN."""
    risk = _series(_RISK, "churn_prob", index=list(range(8)))
    value = _series(_VALUE, "value", index=list(range(100, 108)))

    with pytest.raises(ValueError, match="index"):
        assign_quadrant(risk, value)


def test_length_mismatch_raises() -> None:
    risk = _series(_RISK, "churn_prob")
    value = _series(_VALUE[:-1], "value")

    with pytest.raises(ValueError):
        assign_quadrant(risk, value)


# --- Purity ------------------------------------------------------------------


def test_inputs_are_not_mutated() -> None:
    risk, value = _paired(_RISK, _VALUE)
    risk_before = risk.copy()
    value_before = value.copy()

    assign_quadrant(risk, value)

    pd.testing.assert_series_equal(risk, risk_before)
    pd.testing.assert_series_equal(value, value_before)


def test_determinism_repeated_calls_agree() -> None:
    risk, value = _paired(_RISK, _VALUE)

    first = assign_quadrant(risk, value)
    second = assign_quadrant(risk, value)

    pd.testing.assert_series_equal(first, second)
