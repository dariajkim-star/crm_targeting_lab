"""Behavioural tests for the churn-risk model (AC1, AC2, AC4).

Behaviour-based: determinism and hyperparameter contracts are checked on the
estimator's declared params / repeated fits, not by re-deriving XGBoost. The
imbalance handling, PR-AUC signal, lift arithmetic and leakage exclusions are
each pinned by a property a plausible mis-implementation would break.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.config import CHURN_TREE_METHOD, RANDOM_SEED
from crm.churn.model import (
    PREDICTOR_COLUMNS,
    build_xy,
    fit_and_compare,
    lift,
    make_baseline,
    make_xgboost,
    pr_auc_cv,
    score_customers,
)


def _features(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "CLIENTNUM": np.arange(n),
        "recency_proxy": rng.integers(0, 6, n),
        "frequency_proxy": rng.integers(10, 140, n),
        "monetary_proxy": rng.uniform(500, 18000, n),
        # extra columns the model must ignore:
        "R_score": 1, "F_score": 1, "M_score": 1, "segment_id": 1,
    })


def _raw_with_signal(features: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    # Attrition depends on frequency (low frequency -> churn), so a real model
    # beats the base rate. Deterministic given seed.
    rng = np.random.default_rng(seed)
    p = 1 / (1 + np.exp((features["frequency_proxy"].to_numpy() - 60) / 15))
    attr = rng.random(len(features)) < p
    return pd.DataFrame({
        "CLIENTNUM": features["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": np.where(attr, "Attrited Customer", "Existing Customer"),
    })


# --- AC1: hyperparameters / imbalance / determinism --------------------------

def test_xgboost_pins_determinism_and_imbalance_params():
    # 30 positives, 70 negatives -> scale_pos_weight = 70/30. AD-7 params fixed.
    y = pd.Series([1] * 30 + [0] * 70)
    params = make_xgboost(y, seed=RANDOM_SEED).get_params()
    assert params["random_state"] == RANDOM_SEED
    assert params["n_jobs"] == 1                       # AD-7: single thread
    assert params["tree_method"] == CHURN_TREE_METHOD  # AD-7: pinned
    assert params["scale_pos_weight"] == pytest.approx(70 / 30)


def test_baseline_handles_imbalance():
    params = make_baseline(pd.Series([1, 0, 0]), seed=RANDOM_SEED).get_params()
    assert params["class_weight"] == "balanced"
    assert params["random_state"] == RANDOM_SEED


def test_scores_are_deterministic_across_runs():
    feat = _features(300, seed=1)
    raw = _raw_with_signal(feat, seed=1)
    a = fit_and_compare(feat, raw, seed=RANDOM_SEED)
    b = fit_and_compare(feat, raw, seed=RANDOM_SEED)
    pd.testing.assert_frame_equal(a.scored, b.scored)


# --- AC1/AC2: PR-AUC beats the base rate, lift arithmetic ---------------------

def test_pr_auc_beats_the_positive_rate_when_signal_exists():
    feat = _features(600, seed=2)
    raw = _raw_with_signal(feat, seed=2)
    x, y = build_xy(feat, raw)
    positive_rate = y.mean()
    auc = pr_auc_cv(lambda yy, s: make_xgboost(yy, s), x, y, seed=RANDOM_SEED)
    # A model with real signal must clear the no-skill PR-AUC (= prevalence).
    assert auc > positive_rate


def test_lift_is_relative_improvement():
    assert lift(0.40, 0.80) == pytest.approx(1.0)   # +100%
    assert lift(0.50, 0.575) == pytest.approx(0.15)  # +15%
    with pytest.raises(ValueError, match="positive"):
        lift(0.0, 0.5)


# --- AC1: leakage exclusion (sprint-status re-audit) -------------------------

def test_predictor_set_excludes_target_and_leakage():
    assert "Attrition_Flag" not in PREDICTOR_COLUMNS
    assert not any(c.startswith("Naive_Bayes_Classifier_") for c in PREDICTOR_COLUMNS)


def test_build_xy_never_puts_target_or_leakage_into_x():
    feat = _features(50, seed=3)
    # inject the real leakage columns + the target into the FEATURES frame:
    feat["Naive_Bayes_Classifier_Attrition_Flag_a_1"] = 1.0
    feat["Attrition_Flag"] = "Existing Customer"
    raw = _raw_with_signal(feat, seed=3)
    x, _ = build_xy(feat, raw)
    assert list(x.columns) == list(PREDICTOR_COLUMNS)
    assert "Attrition_Flag" not in x.columns
    assert not [c for c in x.columns if "Naive_Bayes" in c]


def test_label_maps_only_attrited_to_positive():
    feat = _features(4, seed=4)
    raw = pd.DataFrame({
        "CLIENTNUM": feat["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": ["Attrited Customer", "Existing Customer",
                           "Attrited Customer", "Existing Customer"],
    })
    _, y = build_xy(feat, raw)
    assert y.tolist() == [1, 0, 1, 0]


# --- key hygiene + purity ----------------------------------------------------

def test_build_xy_rejects_duplicate_key():
    feat = _features(10, seed=5)
    dup = pd.concat([feat, feat.iloc[[0]]], ignore_index=True)
    raw = _raw_with_signal(feat, seed=5)
    with pytest.raises(ValueError, match="unique"):
        build_xy(dup, raw)


def test_build_xy_rejects_null_key():
    feat = _features(10, seed=6)
    feat.loc[0, "CLIENTNUM"] = None
    raw = _raw_with_signal(feat, seed=6)
    with pytest.raises(ValueError, match="null"):
        build_xy(feat, raw)


def test_build_xy_rejects_join_that_loses_customers():
    feat = _features(10, seed=7)
    raw = _raw_with_signal(feat, seed=7).iloc[1:]  # drop one customer's label
    with pytest.raises(ValueError, match="lost rows"):
        build_xy(feat, raw)


def test_inputs_are_not_mutated():
    feat = _features(60, seed=8)
    raw = _raw_with_signal(feat, seed=8)
    fbefore, rbefore = feat.copy(deep=True), raw.copy(deep=True)
    fit_and_compare(feat, raw, seed=RANDOM_SEED)
    pd.testing.assert_frame_equal(feat, fbefore)
    pd.testing.assert_frame_equal(raw, rbefore)


def test_score_customers_preserves_index():
    feat = _features(40, seed=9)
    raw = _raw_with_signal(feat, seed=9)
    x, y = build_xy(feat, raw)
    model = make_xgboost(y, RANDOM_SEED).fit(x, y)
    scores = score_customers(model, x)
    assert list(scores.index) == list(x.index)
    assert scores.between(0, 1).all()
