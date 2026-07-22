"""Behavioural tests for the expected-savings formula (story 3-2, CAP-6/FR12).

Why these assertions and not others
-----------------------------------
Re-writing `p * value * rate - cost` in the test and comparing would prove only
that the same expression was typed twice. Each test below names a PROPERTY the
decision frame depends on:

  - MONOTONE in all four inputs. This is what makes the number usable as a
    ranking signal by story 3-3: if a higher churn probability could lower the
    expected saving, "target the top N" would be meaningless.
  - THE SIGN FLIP is where the campaign stops paying for itself, at
    `p * value = cost / rate`. Story 3-4 sweeps the assumptions AROUND this
    boundary, so its location is a contract, not an implementation detail.
  - ONE HARD-CODED ORACLE, computed by hand, so the whole suite cannot drift
    together if the formula is edited.
  - MUTANTS: sign flips, dropped terms, cost added instead of subtracted, and
    probability swapped with value must all be KILLED. The last one matters
    because both are numeric Series and the swap raises no error.
  - COLUMN CONTRACT (AC5): the probability input must be the CALIBRATED column.
    Measured on the real artifact, feeding the raw score inflates the total by
    +19.0% and nothing in the type system notices.
  - VALUE PASS-THROUGH (AC6): AD-11 says `customer_value()` alone defines value.
    The existing guard cannot see `customer_value(df) * 0.02`, so this pins it
    from the consumer side with a sentinel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.campaign.simulate import expected_saving
from crm.config import COST_PER_CONTACT, RETENTION_SUCCESS_RATE


@pytest.fixture
def pair() -> tuple[pd.Series, pd.Series]:
    """A small population with room on both sides of the sign flip."""
    index = pd.Index([101, 102, 103, 104], name="CLIENTNUM")
    prob = pd.Series([0.05, 0.20, 0.50, 0.90], index=index, name="churn_prob_calibrated")
    value = pd.Series([100.0, 500.0, 2000.0, 8000.0], index=index, name="customer_value")
    return prob, value


# --- The hard-coded oracle ---------------------------------------------------


def test_one_hand_computed_case():
    """The single arithmetic anchor. Every other test is a property.

    p=0.40, value=1000, rate=0.25, cost=30
      gross saved   = 0.40 * 1000 * 0.25 = 100.0
      minus contact = 100.0 - 30         =  70.0
    """
    prob = pd.Series([0.40], index=[1])
    value = pd.Series([1000.0], index=[1])

    result = expected_saving(prob, value, retention_rate=0.25, cost_per_contact=30.0)

    assert result.iloc[0] == pytest.approx(70.0)


# --- Monotonicity (the ranking property story 3-3 stands on) -----------------


@pytest.mark.parametrize(
    ("kwargs_low", "kwargs_high"),
    [
        ({"retention_rate": 0.10}, {"retention_rate": 0.50}),
    ],
)
def test_a_higher_retention_rate_saves_more(pair, kwargs_low, kwargs_high):
    prob, value = pair

    low = expected_saving(prob, value, **kwargs_low)
    high = expected_saving(prob, value, **kwargs_high)

    assert (high > low).all()


def test_a_higher_contact_cost_saves_less(pair):
    prob, value = pair

    cheap = expected_saving(prob, value, cost_per_contact=1.0)
    dear = expected_saving(prob, value, cost_per_contact=20.0)

    assert (dear < cheap).all()


def test_a_higher_churn_probability_saves_more(pair):
    """The ranking property: riskier customers are worth more to keep.

    If this ever inverted, story 3-3's "contact the top N" would target the
    customers with the least to gain, and no aggregate in the report would look
    wrong while it happened.
    """
    prob, value = pair
    riskier = prob + 0.05

    assert (expected_saving(riskier, value) > expected_saving(prob, value)).all()


def test_a_more_valuable_customer_saves_more(pair):
    prob, value = pair

    assert (expected_saving(prob, value * 2) > expected_saving(prob, value)).all()


# --- The sign flip -----------------------------------------------------------


def test_the_break_even_point_sits_where_the_formula_says(pair):
    """`p * value = cost / rate` is where the campaign stops paying for itself.

    Asserted as a CROSSING rather than an equality: one customer placed just
    below the boundary must be negative and one just above must be positive.
    Story 3-4 sweeps assumptions around this line, so its location is a
    contract - see the story's 함정 4 on why the resulting "84.8% positive" is
    a product of `cost=5.0`, not a finding.
    """
    boundary = COST_PER_CONTACT / RETENTION_SUCCESS_RATE  # 16.666...
    value = pd.Series([1000.0, 1000.0], index=[1, 2])
    prob = pd.Series([(boundary - 1.0) / 1000.0, (boundary + 1.0) / 1000.0], index=[1, 2])

    result = expected_saving(prob, value)

    assert result.iloc[0] < 0.0
    assert result.iloc[1] > 0.0


def test_exactly_on_the_boundary_is_zero():
    boundary = COST_PER_CONTACT / RETENTION_SUCCESS_RATE
    value = pd.Series([1000.0], index=[1])
    prob = pd.Series([boundary / 1000.0], index=[1])

    assert expected_saving(prob, value).iloc[0] == pytest.approx(0.0)


# --- Mutation kills ----------------------------------------------------------


def test_the_cost_is_subtracted_not_added():
    """Kills the `+ cost` mutant, which no monotonicity test above catches.

    Chosen so the two mutants differ in SIGN, not just magnitude: a customer
    whose gross saving is smaller than the contact cost must end up negative.
    """
    prob = pd.Series([0.01], index=[1])
    value = pd.Series([100.0], index=[1])

    result = expected_saving(prob, value, retention_rate=0.30, cost_per_contact=5.0)

    assert result.iloc[0] < 0.0


def test_the_retention_rate_is_a_factor_not_a_term():
    """Kills `p * value + rate` and `p * value` (rate dropped).

    Doubling the rate must double the GROSS saving, so with the cost held out
    of the way the difference between two rates scales exactly.
    """
    prob = pd.Series([0.50], index=[1])
    value = pd.Series([1000.0], index=[1])

    at_10 = expected_saving(prob, value, retention_rate=0.10, cost_per_contact=0.0).iloc[0]
    at_20 = expected_saving(prob, value, retention_rate=0.20, cost_per_contact=0.0).iloc[0]

    assert at_20 == pytest.approx(2 * at_10)


def test_probability_and_value_are_not_interchangeable():
    """Kills the swapped-arguments mutant.

    Both inputs are numeric Series, so passing them the wrong way round raises
    nothing. The formula multiplies them, so a symmetric case would be blind to
    it - `p * value` is commutative. What is NOT symmetric is the range
    contract: probability lives in [0, 1] and value does not, so the swap is
    caught by validation rather than by arithmetic.
    """
    prob, value = pair_for_swap()

    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        expected_saving(value, prob)


def pair_for_swap() -> tuple[pd.Series, pd.Series]:
    index = pd.Index([1, 2])
    return pd.Series([0.2, 0.8], index=index), pd.Series([300.0, 4000.0], index=index)


# --- AC5: the column contract ------------------------------------------------


def test_the_calibrated_column_and_the_raw_score_give_different_money(pair):
    """AC5. The two columns are interchangeable to the type system and NOT to
    the arithmetic.

    Measured on the real artifact: feeding `churn_score` (raw out-of-fold,
    mean 0.1946) instead of `churn_prob_calibrated` (Platt, mean 0.1607 = the
    observed attrition rate) inflates the total by +19.0%. This test does not
    reproduce that figure - it pins the weaker, always-true statement that the
    function is sensitive to which column it was handed, so a future refactor
    cannot quietly make them equivalent.
    """
    _, value = pair
    index = value.index
    calibrated = pd.Series([0.05, 0.18, 0.45, 0.85], index=index)
    raw_score = pd.Series([0.07, 0.22, 0.52, 0.93], index=index)  # uncalibrated: higher

    assert expected_saving(raw_score, value).sum() > expected_saving(calibrated, value).sum()


def test_the_docstring_names_the_calibrated_column():
    """AC5, from the other side: the contract must be readable at the call site.

    A reviewer choosing between two [0, 1] columns has nothing but the
    signature and the docstring to go on, so the column name is required to
    appear there. Story 3-0 renamed these deliberately; this keeps the rename
    from decaying into a comment nobody updated.
    """
    doc = expected_saving.__doc__ or ""

    assert "churn_prob_calibrated" in doc
    assert "churn_score" in doc


# --- AC6: value pass-through (the 1-2 handover) ------------------------------


def test_the_value_input_is_used_exactly_as_given(pair):
    """AC6. AD-11: `customer_value()` alone defines value - no re-weighting.

    The existing structure guard cannot see `value * 0.02` or `np.log1p(value)`
    because neither reads the source column, so `deferred-work.md` handed 3-2 a
    consumer-side contract test. A sentinel makes any re-scaling visible: with
    rate and cost neutralised, the output must be the sentinel multiplied by
    the probability and nothing else.
    """
    prob = pd.Series([1.0, 1.0, 1.0], index=[1, 2, 3])
    sentinel = pd.Series([7.0, 11.0, 13.0], index=[1, 2, 3])

    result = expected_saving(prob, sentinel, retention_rate=1.0, cost_per_contact=0.0)

    pd.testing.assert_series_equal(result, sentinel, check_names=False)


def test_a_rescaled_value_changes_the_answer(pair):
    """The counterpart: if re-weighting were harmless, AC6 would be pointless.

    Pins that value enters at its RAW scale - the temptation named in 함정 3 is
    to normalise it because cost 5.0 and value 3899 look mismatched.
    """
    prob, value = pair

    assert not np.allclose(
        expected_saving(prob, value).to_numpy(),
        expected_saving(prob, value * 0.02).to_numpy(),
    )


# --- Validation (patterns inherited from 3-1's external review) --------------


def test_an_empty_population_is_refused():
    with pytest.raises(ValueError, match="empty"):
        expected_saving(pd.Series([], dtype=float), pd.Series([], dtype=float))


def test_a_missing_probability_is_refused(pair):
    prob, value = pair
    prob = prob.copy()
    prob.iloc[0] = np.nan

    with pytest.raises(ValueError, match="missing"):
        expected_saving(prob, value)


def test_a_non_finite_value_is_refused(pair):
    prob, value = pair
    value = value.copy()
    value.iloc[0] = np.inf

    with pytest.raises(ValueError, match="non-finite"):
        expected_saving(prob, value)


def test_a_probability_outside_zero_one_is_refused(pair):
    prob, value = pair
    prob = prob.copy()
    prob.iloc[0] = 1.4

    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        expected_saving(prob, value)


def test_mismatched_indexes_are_refused(pair):
    prob, value = pair

    with pytest.raises(ValueError, match="share an index"):
        expected_saving(prob, value.set_axis(value.index[::-1]))


def test_a_duplicated_customer_index_is_refused():
    prob = pd.Series([0.2, 0.3], index=[7, 7])
    value = pd.Series([100.0, 200.0], index=[7, 7])

    with pytest.raises(ValueError, match="duplicated"):
        expected_saving(prob, value)


@pytest.mark.parametrize("rogue_rate", [-0.1, 1.4])
def test_a_retention_rate_outside_zero_one_is_refused(pair, rogue_rate):
    """A rate above 1 would save more customers than are at risk."""
    prob, value = pair

    with pytest.raises(ValueError, match="retention_rate"):
        expected_saving(prob, value, retention_rate=rogue_rate)


def test_a_negative_contact_cost_is_refused(pair):
    """A negative cost is a subsidy, not a campaign - and it would make every
    customer look profitable."""
    prob, value = pair

    with pytest.raises(ValueError, match="cost_per_contact"):
        expected_saving(prob, value, cost_per_contact=-1.0)


# --- Purity and shape --------------------------------------------------------


def test_inputs_are_not_mutated(pair):
    prob, value = pair
    prob_before, value_before = prob.copy(), value.copy()

    expected_saving(prob, value)

    pd.testing.assert_series_equal(prob, prob_before)
    pd.testing.assert_series_equal(value, value_before)


def test_index_is_preserved_and_the_series_is_named(pair):
    """4-1 joins this onto the mart by index; the name becomes the column."""
    prob, value = pair

    result = expected_saving(prob, value)

    assert result.index.equals(prob.index)
    assert result.name == "expected_saving"


def test_the_defaults_come_from_config(pair):
    """AD-4: defaults REFERENCE the constants rather than restating them.

    Passing the config values explicitly must reproduce the default call. If a
    literal were ever inlined in the signature, this breaks the moment the
    constant moves - which is the drift AD-4 exists to prevent (P1's
    `current_cutoff` shipped exactly that).
    """
    prob, value = pair

    explicit = expected_saving(
        prob,
        value,
        retention_rate=RETENTION_SUCCESS_RATE,
        cost_per_contact=COST_PER_CONTACT,
    )

    pd.testing.assert_series_equal(expected_saving(prob, value), explicit)
