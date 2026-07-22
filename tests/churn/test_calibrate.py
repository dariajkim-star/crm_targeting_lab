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
    """Consumers join on the index; 3-2 selects by column name."""
    scores, y = scores_and_labels
    scores.index = pd.Index(range(1000, 1000 + len(scores)))
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


def test_mismatched_lengths_are_refused(scores_and_labels) -> None:
    scores, y = scores_and_labels

    with pytest.raises(ValueError):
        fit_calibrator(scores, y.iloc[:-1])


def test_non_finite_scores_are_refused(scores_and_labels) -> None:
    scores, y = scores_and_labels
    scores.iloc[0] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        fit_calibrator(scores, y)
