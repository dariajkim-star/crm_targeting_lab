"""Behavioural tests for Platt calibration (story 3-0, AC2).

Why these assertions and not others
-----------------------------------
Re-running ``LogisticRegression`` inside the test and comparing would be a
tautology. Each test names a PROPERTY the A2 decision depends on:

  - STRICTLY MONOTONE: this is the whole reason Platt was chosen over isotonic.
    Story 3-1 assigns quadrants by quantile, so a strictly increasing
    calibration cannot move a single customer across a cut. If this property
    ever breaks, 3-1's contract breaks with it - the counterpart test lives in
    ``tests/campaign/test_matrix.py``.
  - MEAN CONVERGES to the observed positive rate - that is what "calibrated"
    buys for 3-2's expected-savings arithmetic.
  - RANK PRESERVED, so PR-AUC is untouched (measured: 0.9507 both sides).
  - FIT ON OOF SCORES: calibrating on in-sample scores would make the
    calibration itself optimistic. The API refuses to hide that choice.
  - DETERMINISM under a fixed seed (AD-7, NFR4).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.churn.calibrate import apply_calibration, fit_calibrator


@pytest.fixture
def scores_and_labels() -> tuple[pd.Series, pd.Series]:
    """A separable-but-overconfident score, the shape OOF output really has."""
    rng = np.random.default_rng(0)
    y = pd.Series([0] * 800 + [1] * 200)
    raw = np.where(y == 1, rng.uniform(0.55, 0.999, len(y)), rng.uniform(0.001, 0.6, len(y)))
    return pd.Series(raw, name="churn_score"), y


def test_calibration_is_strictly_monotone(scores_and_labels) -> None:
    """THE property story 3-1 depends on.

    isotonic was rejected precisely because it is only NON-decreasing: it
    collapses distinct scores onto plateaus, and a plateau spanning a quantile
    cut carries everyone on it across (measured: 58 reassignments). Platt keeps
    every distinct score distinct, so the ordering - and therefore every
    quadrant - is untouched.
    """
    scores, y = scores_and_labels
    calibrator = fit_calibrator(scores, y)

    probe = pd.Series(np.linspace(0.001, 0.999, 500))
    calibrated = apply_calibration(calibrator, probe)

    assert (calibrated.diff().dropna() > 0).all()


def test_distinct_scores_stay_distinct(scores_and_labels) -> None:
    """The plateau check, stated as a count rather than a shape."""
    scores, y = scores_and_labels
    calibrator = fit_calibrator(scores, y)

    calibrated = apply_calibration(calibrator, scores)

    assert calibrated.nunique() == scores.nunique()


def test_mean_moves_towards_the_observed_positive_rate(scores_and_labels) -> None:
    """What calibration buys 3-2: the number can be multiplied by money."""
    scores, y = scores_and_labels
    calibrator = fit_calibrator(scores, y)

    calibrated = apply_calibration(calibrator, scores)

    assert abs(calibrated.mean() - y.mean()) < abs(scores.mean() - y.mean())
    assert calibrated.mean() == pytest.approx(y.mean(), abs=0.02)


def test_ranking_is_preserved_exactly(scores_and_labels) -> None:
    """Calibration must not cost ranking quality (measured PR-AUC 0.9507 both)."""
    scores, y = scores_and_labels
    calibrator = fit_calibrator(scores, y)

    calibrated = apply_calibration(calibrator, scores)

    assert (scores.rank(method="first") == calibrated.rank(method="first")).all()


def test_output_stays_inside_zero_one(scores_and_labels) -> None:
    scores, y = scores_and_labels
    calibrator = fit_calibrator(scores, y)

    calibrated = apply_calibration(calibrator, pd.Series([0.0, 0.5, 1.0]))

    assert ((calibrated >= 0.0) & (calibrated <= 1.0)).all()


def test_index_and_name_are_preserved(scores_and_labels) -> None:
    """Consumers join on the index; 3-2 selects by column name.

    Both sides are reindexed, not just the scores: `fit_calibrator` now requires
    the pair to share an index, so moving one alone is no longer a valid call -
    it is the very mispairing the guard exists to catch.
    """
    scores, y = scores_and_labels
    moved = pd.Index(range(1000, 1000 + len(scores)))
    scores.index = moved
    y.index = moved
    calibrator = fit_calibrator(scores, y)

    calibrated = apply_calibration(calibrator, scores)

    assert calibrated.index.equals(scores.index)
    assert calibrated.name == "churn_prob_calibrated"


def test_inputs_are_not_mutated(scores_and_labels) -> None:
    scores, y = scores_and_labels
    before = scores.copy()

    apply_calibration(fit_calibrator(scores, y), scores)

    pd.testing.assert_series_equal(scores, before)


def test_repeated_fits_agree(scores_and_labels) -> None:
    scores, y = scores_and_labels

    first = apply_calibration(fit_calibrator(scores, y), scores)
    second = apply_calibration(fit_calibrator(scores, y), scores)

    pd.testing.assert_series_equal(first, second)


# --- Fail-fast ---------------------------------------------------------------


def test_empty_input_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        fit_calibrator(pd.Series([], dtype=float), pd.Series([], dtype=int))


def test_a_single_class_is_refused() -> None:
    """A calibrator fit on one class would emit a constant - a plateau across
    the WHOLE range, which is exactly what this story rejected isotonic for."""
    scores = pd.Series([0.1, 0.2, 0.3, 0.4])

    with pytest.raises(ValueError, match="both classes"):
        fit_calibrator(scores, pd.Series([0, 0, 0, 0]))


def test_a_reversed_signal_is_refused() -> None:
    """The monotonicity above is a fact about the DATA, so it needs a guard.

    ``test_calibration_is_strictly_monotone`` proves the property on one
    well-behaved fixture. Feed the same fitter a score that ranks backwards and
    the fitted sigmoid is strictly DECREASING - and nothing downstream notices,
    because an intercept still puts the mean on the observed rate. Measured
    before the guard existed: coef=-10.49, mean 0.2001 against an actual 0.2000.
    """
    rng = np.random.default_rng(0)
    y = pd.Series([0] * 800 + [1] * 200)
    backwards = np.where(y == 1, rng.uniform(0.001, 0.45, len(y)), rng.uniform(0.4, 0.999, len(y)))

    with pytest.raises(ValueError, match="not strictly increasing"):
        fit_calibrator(pd.Series(backwards, name="churn_score"), y)


def test_a_score_with_no_signal_is_refused() -> None:
    """The quiet case: noise, not reversal.

    A score unrelated to the outcome yields a coefficient near zero of either
    sign - here -0.185. The calibrated column would be an almost-flat band at
    the base rate, which reads as a plausible probability while carrying no
    information. This is the failure the single-class check already refuses,
    arriving through a door that check does not cover.
    """
    rng = np.random.default_rng(7)
    y = pd.Series([0] * 800 + [1] * 200)
    noise = pd.Series(rng.uniform(0.0, 1.0, len(y)), name="churn_score")

    with pytest.raises(ValueError, match="not strictly increasing"):
        fit_calibrator(noise, y)


def test_mismatched_lengths_are_refused(scores_and_labels) -> None:
    scores, y = scores_and_labels

    with pytest.raises(ValueError):
        fit_calibrator(scores, y.iloc[:-1])


def test_a_mismatched_index_is_refused(scores_and_labels) -> None:
    """Same length, same customers, different order - the silent mispairing.

    The fit drops to numpy and joins by position, so this produces a perfectly
    well-formed sigmoid fitted against the wrong customers' outcomes. No metric
    downstream can tell it from a good fit, which is why it is refused here
    rather than tolerated.
    """
    scores, y = scores_and_labels

    with pytest.raises(ValueError, match="share an index"):
        fit_calibrator(scores, y.set_axis(y.index[::-1]))


def test_a_non_finite_label_is_refused(scores_and_labels) -> None:
    """A missing outcome is not a negative one."""
    scores, y = scores_and_labels
    y = y.astype(float)
    y.iloc[0] = float("nan")

    with pytest.raises(ValueError, match="finite outcome"):
        fit_calibrator(scores, y)


def test_non_finite_scores_are_refused(scores_and_labels) -> None:
    scores, y = scores_and_labels
    scores.iloc[0] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        fit_calibrator(scores, y)
