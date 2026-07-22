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


def _validate_scores(scores: pd.Series, caller: str) -> np.ndarray:
    # `caller` is named rather than inferred: both public functions share this
    # helper, and a message that says "fit_calibrator" while the failure came
    # from apply_calibration sends the reader to a call that never happened.
    if scores.empty:
        raise ValueError(
            f"{caller} received an empty score series. An empty population "
            f"cannot state what a probability means."
        )
    values = scores.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            f"{caller} requires finite scores; NaN or infinity would be "
            f"carried straight into the fitted sigmoid."
        )
    return values


def fit_calibrator(oof_scores: pd.Series, y: pd.Series) -> LogisticRegression:
    """Fit Platt scaling: a logistic regression on the raw score.

    Args:
        oof_scores: Out-of-fold risk scores - each produced by a model that did
            NOT train on that customer. Passing in-sample scores here is a
            silent correctness bug, not an error this function can detect.
        y: The observed binary outcome. Must share ``oof_scores``' index - the
            fit joins the two by position, so the index is the only thing that
            can prove the pair belongs to the same customer.

    Returns:
        The fitted calibrator, to be handed to :func:`apply_calibration`. It is
        returned rather than applied so the caller can put it in the AD-5
        artifact bundle - the calibrator is a second FITTED object, and an
        identity record that covered only the model would let the calibrator be
        swapped without the ``artifact_id`` changing.

    Raises:
        ValueError: on mismatched lengths or indexes, empty input, non-finite
            scores or labels, a single-class ``y``, or a fit that is not
            strictly increasing.
    """
    # Pairing is checked BEFORE the contents of either side. A collapsed upstream
    # join arrives here as an empty or short score series, and reporting that as
    # "empty score series" names the symptom while hiding the cause.
    if len(oof_scores) != len(y):
        raise ValueError(
            f"fit_calibrator needs one label per score: got {len(oof_scores)} "
            f"and {len(y)}. A length mismatch means the score and the outcome "
            f"came from different populations, not that one of them is short."
        )
    if not oof_scores.index.equals(y.index):
        # `crm/campaign/matrix.py` refuses mismatched indexes for exactly this
        # reason and this pairing is the more dangerous one: the fit below drops
        # to numpy and joins by POSITION, so a reordering upstream produces a
        # perfectly plausible sigmoid fitted against the wrong customers'
        # outcomes. Nothing downstream could distinguish it from a good fit.
        raise ValueError(
            "fit_calibrator needs the score and the label to share an index; "
            "they are aligned by position, so a differing index means the pair "
            "is not the same customer."
        )
    values = _validate_scores(oof_scores, "fit_calibrator")
    if not np.isfinite(y.to_numpy(dtype=float)).all():
        raise ValueError(
            "fit_calibrator requires a finite outcome for every customer; a "
            "missing label is not a negative one."
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
    #
    # Stated exactly, because the sentence above reads like "no regularisation"
    # and that is not what this line does: sklearn's default is `penalty="l2",
    # C=1.0`, so a mild shrinkage IS applied. Not swept is not the same as not
    # present. On this artifact it is immaterial - the fitted coefficient is
    # +10.4, far from where C=1.0 would bend it, and the calibrated mean lands
    # on the observed rate (0.1607) exactly. Making it explicit (`C=1e10`, or a
    # named config constant) is deferred rather than dismissed: it would move
    # the calibrated probabilities slightly, and story 3-2 is about to fix its
    # expected-savings baseline on them. The quadrants would not move either
    # way - monotonicity is what protects them, not the penalty.
    model = LogisticRegression().fit(values.reshape(-1, 1), y.to_numpy())

    # The single property this module exists to guarantee is NOT guaranteed by
    # the fit - it is a fact about the data. A score that ranks backwards (or
    # not at all) produces a non-positive coefficient, and `apply_calibration`
    # then becomes strictly DECREASING while the mean still lands exactly on the
    # observed rate. No downstream metric would show it: measured on a reversed
    # signal, coef=-10.49 with mean 0.2001 against an actual 0.2000. Refusing a
    # single-class `y` above but accepting a reversed fit here would be the same
    # omission with a different face.
    coef = float(model.coef_[0][0])
    if coef <= 0.0:
        raise ValueError(
            f"Platt fit is not strictly increasing (coef={coef:.6g}). The "
            f"calibrated probability would not rank customers the way the score "
            f"does, so expected-savings arithmetic built on it would be inverted "
            f"or flat. This means the scores do not predict the outcome, not "
            f"that the calibration needs tuning."
        )
    return model


def apply_calibration(calibrator: LogisticRegression, scores: pd.Series) -> pd.Series:
    """Map raw scores onto calibrated probabilities.

    Returns:
        ``Series[float]`` named :data:`CALIBRATED_COLUMN`, indexed exactly like
        ``scores``. Strictly increasing in the input - enforced at fit time by
        :func:`fit_calibrator`, not assumed here - so the ranking is preserved
        exactly and story 3-2's expected savings order customers the same way
        the 2x2 does. (Story 3-1 reads ``churn_score`` directly and so does not
        depend on this; the two-track split moved the exposure to 3-2.)

    Raises:
        ValueError: on empty input or non-finite scores.
    """
    values = _validate_scores(scores, "apply_calibration")
    calibrated = calibrator.predict_proba(values.reshape(-1, 1))[:, 1]
    return pd.Series(calibrated, index=scores.index, name=CALIBRATED_COLUMN)
