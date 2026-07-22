"""Platt calibration of out-of-fold churn scores (story 3-0, A2 decision).

What this module is for
-----------------------
Two different consumers need two different numbers from the same model, and
story 3-0 stopped making one column serve both:

    quadrant_official (3-1)  <- churn_score            raw OOF, RANK only
    expected_saving   (3-2)  <- churn_prob_calibrated  probability, MAGNITUDE

The 2x2 cuts customers at quantiles, so it only needs the ordering. The
expected-savings formula multiplies by money, so it needs a number that means
what it says. This module produces the second from the first.

Why Platt and not isotonic (A2, measured 2026-07-22)
----------------------------------------------------
Both put the mean on the observed attrition rate (0.1607). They differ in what
they do to the ORDER:

    Platt      strictly increasing  -> quadrant reassignments:  0
    isotonic   non-decreasing       -> quadrant reassignments: 58

Isotonic collapsed 10,127 distinct scores onto 95 values; 101 customers landed
exactly on the 3-1 cut and the plateau carried them across it. Platt keeps every
distinct score distinct, so story 3-1's assignments are provably untouched -
`test_calibrate.py` pins the monotonicity and `test_matrix.py` pins the
consequence from the other side. Platt also costs no ranking quality (PR-AUC
0.9507 either way; isotonic 0.9492).

The cost, stated plainly: Platt assumes the miscalibration has a sigmoid shape.
If a future model's distortion is not sigmoidal, Platt will underfit it where
isotonic would not. On the current artifact it lands the mean exactly, so the
assumption holds here; a later story that changes the model must re-check rather
than inherit this conclusion.

Fit on OUT-OF-FOLD scores, never in-sample
------------------------------------------
`fit_calibrator` is fed the scores a model produced for customers it did not
train on. Calibrating on in-sample scores would make the calibration itself
optimistic - the correction would be learned from the same overconfidence it is
supposed to remove. The caller owns that discipline; this module cannot verify
where its input came from, so `crm/churn/model.py` is the single place the
wiring is made and tested.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk.
Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

__all__ = ["CALIBRATED_COLUMN", "apply_calibration", "fit_calibrator"]

CALIBRATED_COLUMN = "churn_prob_calibrated"


def _validate_scores(scores: pd.Series) -> np.ndarray:
    if scores.empty:
        raise ValueError(
            "fit_calibrator received an empty score series. An empty population "
            "cannot state what a probability means."
        )
    values = scores.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            "fit_calibrator requires finite scores; NaN or infinity would be "
            "carried straight into the fitted sigmoid."
        )
    return values


def fit_calibrator(oof_scores: pd.Series, y: pd.Series) -> LogisticRegression:
    """Fit Platt scaling: a logistic regression on the raw score.

    Args:
        oof_scores: Out-of-fold risk scores - each produced by a model that did
            NOT train on that customer. Passing in-sample scores here is a
            silent correctness bug, not an error this function can detect.
        y: The observed binary outcome, aligned positionally with ``oof_scores``.

    Returns:
        The fitted calibrator, to be handed to :func:`apply_calibration`. It is
        returned rather than applied so the caller can put it in the AD-5
        artifact bundle - the calibrator is a second FITTED object, and an
        identity record that covered only the model would let the calibrator be
        swapped without the ``artifact_id`` changing.

    Raises:
        ValueError: on empty input, non-finite scores, mismatched lengths, or a
            single-class ``y``.
    """
    values = _validate_scores(oof_scores)
    if len(oof_scores) != len(y):
        raise ValueError(
            f"fit_calibrator needs one label per score: got {len(oof_scores)} "
            f"and {len(y)}."
        )
    classes = set(pd.unique(y))
    if classes != {0, 1}:
        raise ValueError(
            f"fit_calibrator needs both classes 0 and 1, got {sorted(classes)}. "
            f"A single-class fit emits a constant - a plateau across the whole "
            f"range, which is what this story rejected isotonic for."
        )

    # No regularisation sweep, no class_weight: Platt scaling is a one-parameter
    # (plus intercept) correction by definition, and anything richer would start
    # re-learning the ranking the model already produced.
    return LogisticRegression().fit(values.reshape(-1, 1), y.to_numpy())


def apply_calibration(calibrator: LogisticRegression, scores: pd.Series) -> pd.Series:
    """Map raw scores onto calibrated probabilities.

    Returns:
        ``Series[float]`` named :data:`CALIBRATED_COLUMN`, indexed exactly like
        ``scores``. Strictly increasing in the input, so the ranking - and every
        story 3-1 quadrant derived from it - is preserved exactly.

    Raises:
        ValueError: on empty input or non-finite scores.
    """
    values = _validate_scores(scores)
    calibrated = calibrator.predict_proba(values.reshape(-1, 1))[:, 1]
    return pd.Series(calibrated, index=scores.index, name=CALIBRATED_COLUMN)
