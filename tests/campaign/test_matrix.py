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
  - RANK-ONLY, AND ITS LIMIT: a STRICTLY increasing transform of the risk
    scores leaves every assignment unchanged, but a monotone NON-decreasing one
    (isotonic calibration) does not - a plateau spanning the cut moves people
    across it. Both directions are pinned, because the weaker claim is the one
    the report is allowed to make (external review, 2026-07-22).
  - LABELS come from the Enum, never free strings (AC1)
  - FAIL-FAST on empty input, NaN, and misaligned indexes (1-6a/1-6b/1-7
    discipline: no quiet tolerance)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.campaign.matrix import assign_quadrant, quadrant_thresholds
from crm.config import BOUNDARY_UPPER_INCLUSIVE, QUADRANT_RULE, Quadrant


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

    result = assign_quadrant(risk, value).labels

    assert len(result) == len(risk)
    assert result.index.equals(risk.index)
    assert set(result.unique()) <= {q.value for q in Quadrant}
    assert result.notna().all()


def test_labels_are_enum_values_not_free_strings() -> None:
    """A refactor that hand-types 'save_first' somewhere must not drift."""
    risk, value = _paired(_RISK, _VALUE)

    result = assign_quadrant(risk, value).labels

    # Enum membership, not string equality: a typo'd literal fails to construct.
    for label in result.unique():
        assert Quadrant(label) in Quadrant


def test_all_four_quadrants_are_reachable() -> None:
    """A rule that can never emit one cell would pass the 'exactly one' test."""
    risk, value = _paired(_RISK, _VALUE)

    result = assign_quadrant(risk, value).labels

    assert set(result.unique()) == {q.value for q in Quadrant}


# --- AC1/AC2: monotonicity - the probe that kills axis swaps -----------------


def test_raising_risk_never_moves_a_customer_to_a_lower_risk_quadrant() -> None:
    risk, value = _paired(_RISK, _VALUE)
    baseline = assign_quadrant(risk, value).labels

    # Lift the lowest-risk customer above the risk threshold. Stays inside
    # [0, 1] - the axis is a probability and the domain check now enforces it.
    lifted = risk.copy()
    lifted.iloc[0] = 0.99

    result = assign_quadrant(lifted, value).labels

    high_risk = {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}
    assert baseline.iloc[0] not in high_risk
    assert result.iloc[0] in high_risk


def test_raising_value_never_moves_a_customer_to_a_lower_value_quadrant() -> None:
    risk, value = _paired(_RISK, _VALUE)
    baseline = assign_quadrant(risk, value).labels

    lifted = value.copy()
    lifted.iloc[0] = value.max() * 10

    result = assign_quadrant(risk, lifted).labels

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

    result = assign_quadrant(risk, value).labels

    assert risk.iloc[3] == thresholds.risk  # genuinely on the edge
    assert result.iloc[3] == Quadrant.SAVE_FIRST.value


def test_the_customer_exactly_on_the_value_cut_counts_as_high_value() -> None:
    """Same edge rule on the other axis (index 2 sits exactly on 30.0)."""
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)

    thresholds = quadrant_thresholds(risk, value)
    result = assign_quadrant(risk, value).labels

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
    result = assign_quadrant(risk, value).labels

    assert risk.iloc[2] < thresholds.risk
    assert result.iloc[2] not in {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}


def test_the_cut_separates_neighbouring_customers() -> None:
    """On the n=8 fixture the cut falls strictly BETWEEN two order statistics.

    The pair straddling it must land on opposite sides - a rule that collapsed
    every row into one cell would still satisfy the exhaustiveness test.
    """
    risk, value = _paired(_RISK, _VALUE)

    thresholds = quadrant_thresholds(risk, value)
    result = assign_quadrant(risk, value).labels

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
    baseline = assign_quadrant(risk, value).labels

    # Monotone but strongly non-linear - exactly the shape of the measured
    # miscalibration (fine at the extremes, distorted in the middle).
    recalibrated = risk**3 / (risk**3 + (1 - risk) ** 3)

    result = assign_quadrant(recalibrated, value).labels

    pd.testing.assert_series_equal(result, baseline)


def test_rank_invariance_also_holds_when_the_cut_sits_on_a_data_point() -> None:
    """The other half of the invariance argument, which n=8 does not exercise.

    `Series.quantile` interpolates, so there are two cases and they need
    different reasoning:

      - cut strictly BETWEEN two order statistics (the n=8 fixture): the
        interpolated cut moves to sit between the same two transformed
        statistics, so the same customers clear it.
      - cut exactly ON an order statistic (this n=5 fixture): the quantile
        returns that value itself, and the transform maps it to the new cut.

    Only the first case was covered. Without this test the report's general
    claim - that A2's calibration decision cannot move any assignment - would
    be broader than the evidence behind it.
    """
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)
    thresholds = quadrant_thresholds(risk, value)
    assert risk.eq(thresholds.risk).any()  # the cut really is a data point

    baseline = assign_quadrant(risk, value).labels
    recalibrated = risk**3 / (risk**3 + (1 - risk) ** 3)

    result = assign_quadrant(recalibrated, value).labels

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

    result = assign_quadrant(risk, value).labels

    assert list(result) == [
        Quadrant.ACCEPT_CHURN.value,
        Quadrant.ACCEPT_CHURN.value,
        Quadrant.LOW_COST_KEEP.value,
        Quadrant.SAVE_FIRST.value,
    ]


def test_watch_cell_is_high_risk_and_low_value() -> None:
    """Pins the WATCH label to its cell - a relabelling mutation dies here."""
    risk, value = _paired([0.1, 0.2, 0.3, 0.4], [40.0, 30.0, 20.0, 10.0])

    result = assign_quadrant(risk, value).labels

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

    first = assign_quadrant(risk, value).labels
    second = assign_quadrant(risk, value).labels

    pd.testing.assert_series_equal(first, second)


# --- Review round 1 (external, 2026-07-22): rule validation reaches sweeps ----


def test_an_unsupported_boundary_rule_is_refused_not_ignored() -> None:
    """M7. `boundary` was declared in config and never read - a rule object
    could claim `lower_exclusive` and silently get the standard `>=`."""
    risk, value = _paired(_RISK, _VALUE)

    with pytest.raises(ValueError, match="boundary"):
        assign_quadrant(risk, value, rule=QUADRANT_RULE.replace(boundary="lower_exclusive"))


def test_the_shipped_rule_declares_the_boundary_the_code_implements() -> None:
    assert QUADRANT_RULE.boundary == BOUNDARY_UPPER_INCLUSIVE


@pytest.mark.parametrize("quantile", [0.0, 1.0, -0.1, 1.5])
def test_a_degenerate_quantile_passed_at_the_call_site_is_refused(quantile: float) -> None:
    """M8. config validates its own constant at import time, but a sweep
    building a rule with `replace()` bypassed that entirely."""
    risk, value = _paired(_RISK, _VALUE)

    with pytest.raises(ValueError, match="between 0 and 1"):
        assign_quadrant(risk, value, rule=QUADRANT_RULE.replace(risk_quantile=quantile))
    with pytest.raises(ValueError, match="between 0 and 1"):
        assign_quadrant(risk, value, rule=QUADRANT_RULE.replace(value_quantile=quantile))


# --- Review round 1: labels and thresholds cannot drift apart ----------------


def test_labels_and_thresholds_come_from_one_computation() -> None:
    """M9. The mart (4-1) must not be able to pair a full-population label
    column with a cut computed on a filtered subset."""
    risk, value = _paired(_RISK, _VALUE)

    assignment = assign_quadrant(risk, value)

    assert assignment.population_size == len(risk)
    assert assignment.rule == QUADRANT_RULE
    standalone = quadrant_thresholds(risk, value)
    assert assignment.thresholds == standalone
    # The labels really were cut at the thresholds carried alongside them.
    high_risk = {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}
    for score, label in zip(risk, assignment.labels, strict=True):
        assert (score >= assignment.thresholds.risk) == (label in high_risk)


# --- Review round 1: the rank-only claim has a boundary ----------------------


def test_a_plateau_producing_calibration_DOES_change_assignments() -> None:
    """M10. The counter-example that narrows AC6.

    Isotonic regression - the likeliest outcome of retro action A2, and the
    method already used to measure the miscalibration - is monotone
    NON-decreasing: it collapses distinct scores onto shared values. A plateau
    spanning the cut carries everyone on it across.

    This test asserts the FAILURE, deliberately. The report is not allowed to
    say "A2 cannot change a single assignment"; it may only say that a strictly
    increasing recalibration cannot. If someone later makes the assignment
    robust to plateaus, this test should fail and the docs be widened again.
    """
    risk, value = _paired(_EDGE_RISK, _EDGE_VALUE)
    baseline = assign_quadrant(risk, value).labels

    flattened = _series([0.0, 0.0, 0.0, 0.0, 1.0], "churn_prob")
    result = assign_quadrant(flattened, value).labels

    assert not result.equals(baseline)
    high_risk = {Quadrant.SAVE_FIRST.value, Quadrant.WATCH.value}
    assert (baseline.isin(high_risk)).sum() == 2
    assert (result.isin(high_risk)).sum() == 5


# --- Review round 1: axis domain --------------------------------------------


def test_infinity_on_the_risk_axis_is_refused() -> None:
    """M11. One inf drags the cut to inf; an all-inf axis makes it NaN and
    labels the entire base low behind a RuntimeWarning."""
    risk, value = _paired([0.1, 0.2, 0.3, float("inf")], [1.0, 2.0, 3.0, 4.0])

    with pytest.raises(ValueError, match="non-finite"):
        assign_quadrant(risk, value)


def test_an_all_infinite_axis_is_refused_before_the_quantile_goes_nan() -> None:
    risk, value = _paired([float("inf")] * 4, [1.0, 2.0, 3.0, 4.0])

    with pytest.raises(ValueError, match="non-finite"):
        assign_quadrant(risk, value)


def test_infinity_on_the_value_axis_is_refused() -> None:
    risk, value = _paired([0.1, 0.2, 0.3, 0.4], [1.0, 2.0, 3.0, float("inf")])

    with pytest.raises(ValueError, match="non-finite"):
        assign_quadrant(risk, value)


@pytest.mark.parametrize("rogue", [-0.4, 1.7])
def test_a_risk_score_outside_zero_one_is_refused(rogue: float) -> None:
    """M12. `churn_prob` is a probability by contract - a score on some other
    scale would still produce perfectly plausible quadrants."""
    risk, value = _paired([0.1, 0.2, rogue], [1.0, 2.0, 3.0])

    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        assign_quadrant(risk, value)


def test_the_value_axis_has_no_range_check() -> None:
    """Deliberate asymmetry: `customer_value()` promises a raw scale, not
    non-negativity, and this module may not invent a contract for it (AD-11)."""
    risk, value = _paired([0.1, 0.2, 0.3, 0.4], [-50.0, 0.0, 10.0, 20.0])

    assign_quadrant(risk, value)  # must not raise


# --- Review round 1: population integrity ------------------------------------


def test_a_duplicated_customer_index_is_refused() -> None:
    """M13. Both axes sharing the same duplication passes the index-equality
    check, so a fan-out join would hand one customer two official quadrants
    and inflate the population the cuts are computed from."""
    risk = _series([0.1, 0.9, 0.2, 0.3], "churn_prob", index=[101, 101, 102, 103])
    value = _series([100.0, 200.0, 300.0, 400.0], "value", index=[101, 101, 102, 103])

    with pytest.raises(ValueError, match="duplicate"):
        assign_quadrant(risk, value)


@pytest.mark.parametrize(
    ("label", "scores"),
    [
        ("ties away from the cut", [0.1, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]),
        ("ties sitting ON the cut", [0.1, 0.2, 0.3, 0.4, 0.4, 0.4, 0.5, 0.6]),
        ("heavy ties, two clusters", [0.2, 0.2, 0.2, 0.2, 0.8, 0.8, 0.8, 0.8]),
        ("every score identical", [0.3] * 8),
    ],
)
def test_strict_monotone_invariance_survives_ties(label: str, scores: list[float]) -> None:
    """Ties do not break the strictly-increasing half of the AC6 claim.

    The report says strictly increasing recalibration is safe. A strictly
    increasing map is injective, so it preserves ties rather than creating or
    merging them - which is exactly what separates it from isotonic. Pinned
    because the claim is stated generally and duplicated scores are the obvious
    place a general claim goes wrong (raised while preparing the re-review).
    """
    risk = _series(scores, "churn_prob")
    value = _series(_VALUE, "value")

    baseline = assign_quadrant(risk, value).labels
    recalibrated = risk**3 / (risk**3 + (1 - risk) ** 3)

    result = assign_quadrant(recalibrated, value).labels

    pd.testing.assert_series_equal(result, baseline)
