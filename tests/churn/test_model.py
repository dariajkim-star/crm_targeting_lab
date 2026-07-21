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


def test_baseline_handles_imbalance_and_scales():
    # Baseline is a Pipeline: StandardScaler (L2 logistic is not scale-invariant,
    # review Med-5) + balanced logistic with the seed injected.
    pipe = make_baseline(pd.Series([1, 0, 0]), seed=RANDOM_SEED)
    params = pipe.get_params()
    assert params["logisticregression__class_weight"] == "balanced"
    assert params["logisticregression__random_state"] == RANDOM_SEED
    assert "standardscaler" in dict(pipe.named_steps)


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
    with pytest.raises(ValueError, match="sets differ"):
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


# --- review round: label vocabulary / key sets / CV validity (High 2-3, Med 4) -


def test_unknown_label_value_is_rejected_not_zeroed():
    # review High-2: "UNKNOWN", trailing whitespace, typos etc. were silently
    # scored as existing customers. They must fail loudly.
    feat = _features(6, seed=10)
    raw = _raw_with_signal(feat, seed=10)
    raw.loc[0, "Attrition_Flag"] = "Attrited Customer "  # trailing space
    with pytest.raises(ValueError, match="unexpected Attrition_Flag"):
        build_xy(feat, raw)


def test_null_label_is_rejected():
    feat = _features(6, seed=11)
    raw = _raw_with_signal(feat, seed=11)
    raw.loc[0, "Attrition_Flag"] = None
    with pytest.raises(ValueError, match="nulls"):
        build_xy(feat, raw)


def test_raw_only_customer_is_rejected():
    # review High-3: a customer with a label but no features means the feature
    # stage dropped someone - the training population is corrupted, not "a
    # normal subset".
    feat = _features(10, seed=12)
    raw = _raw_with_signal(_features(11, seed=12), seed=12)  # one extra customer
    with pytest.raises(ValueError, match="sets differ"):
        build_xy(feat, raw)


def test_same_size_but_different_customers_is_rejected():
    feat = _features(10, seed=13)
    raw = _raw_with_signal(feat, seed=13)
    raw.loc[0, "CLIENTNUM"] = 999  # same length, different membership
    with pytest.raises(ValueError, match="sets differ"):
        build_xy(feat, raw)


def test_single_class_y_is_rejected():
    # review Med-4: all-negative y crashed inside XGBoost with a cryptic error.
    y_all_zero = pd.Series([0] * 50)
    with pytest.raises(ValueError, match="both classes"):
        make_xgboost(y_all_zero)
    x = pd.DataFrame({"a": range(50)})
    with pytest.raises(ValueError, match="both classes"):
        pr_auc_cv(lambda yy, s: make_xgboost(yy, s), x, y_all_zero)


def test_minority_below_folds_is_rejected():
    y = pd.Series([1] * 3 + [0] * 47)  # 3 positives < 5 folds
    x = pd.DataFrame({"a": range(50)})
    with pytest.raises(ValueError, match="below n_splits"):
        pr_auc_cv(lambda yy, s: make_xgboost(yy, s), x, y, n_splits=5)


def test_nan_predictor_is_rejected():
    feat = _features(10, seed=14)
    feat.loc[0, "monetary_proxy"] = float("nan")
    raw = _raw_with_signal(_features(10, seed=14), seed=14)
    with pytest.raises(ValueError, match="NaN"):
        build_xy(feat, raw)


# --- review round: CV metrics invariant to row order (Med 7) ------------------


def test_cv_metrics_are_invariant_to_row_order():
    feat = _features(300, seed=15)
    raw = _raw_with_signal(feat, seed=15)
    a = fit_and_compare(feat, raw, seed=RANDOM_SEED)
    shuffled = feat.sample(frac=1, random_state=99).reset_index(drop=True)
    b = fit_and_compare(shuffled, raw, seed=RANDOM_SEED)
    assert a.baseline_pr_auc == pytest.approx(b.baseline_pr_auc)
    assert a.xgboost_pr_auc == pytest.approx(b.xgboost_pr_auc)
    assert a.pr_auc_lift == pytest.approx(b.pr_auc_lift)
    sa = a.scored.sort_values("CLIENTNUM").reset_index(drop=True)
    sb = b.scored.sort_values("CLIENTNUM").reset_index(drop=True)
    pd.testing.assert_frame_equal(sa, sb)


# --- review round: CV must evaluate on HELD-OUT data only (Med 8) -------------


def test_cv_never_scores_training_rows():
    # A spy estimator that remembers its training rows and explodes if asked to
    # score any of them - kills the "evaluate on the train fold" leakage mutation
    # (review Med-8: `auc > positive_rate` cannot see that).
    feat = _features(100, seed=16)
    raw = _raw_with_signal(feat, seed=16)
    x, y = build_xy(feat, raw)

    class LeakDetector:
        def __init__(self):
            self.train_ids = None

        def fit(self, xx, yy):
            self.train_ids = set(xx.index)
            self.rate = float(yy.mean())
            return self

        def predict_proba(self, xx):
            overlap = set(xx.index) & self.train_ids
            if overlap:
                raise AssertionError(f"CV scored {len(overlap)} TRAINING rows")
            out = np.column_stack([np.full(len(xx), 1 - self.rate), np.full(len(xx), self.rate)])
            return out

    pr_auc_cv(lambda yy, s: LeakDetector(), x, y, n_splits=4)  # must not raise


def test_fit_and_compare_wires_each_metric_to_its_own_model(monkeypatch):
    # review Med-9: swapping the baseline/xgboost metrics (or hardcoding one)
    # must fail. Patch pr_auc_cv to return a recognisable value per estimator
    # family and assert each lands in its own field.
    import crm.churn.model as mod

    feat = _features(60, seed=17)
    raw = _raw_with_signal(feat, seed=17)

    def fake_pr_auc(make_estimator, x, y, seed=0, n_splits=5):
        est = make_estimator(y, mod.RANDOM_SEED)
        return 0.111 if isinstance(est, mod.Pipeline) else 0.999

    monkeypatch.setattr(mod, "pr_auc_cv", fake_pr_auc)
    result = mod.fit_and_compare(feat, raw)
    assert result.baseline_pr_auc == pytest.approx(0.111)   # Pipeline = baseline
    assert result.xgboost_pr_auc == pytest.approx(0.999)
    assert result.pr_auc_lift == pytest.approx((0.999 - 0.111) / 0.111)


# --- review round: real leakage column names (Low 11) -------------------------

_REAL_LEAK_COLUMNS = (
    "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
    "Dependent_count_Education_Level_Months_Inactive_12_mon_1",
    "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
    "Dependent_count_Education_Level_Months_Inactive_12_mon_2",
)


def test_real_full_leakage_columns_never_enter_x():
    feat = _features(30, seed=18)
    for col in _REAL_LEAK_COLUMNS:
        feat[col] = 0.5
    raw = _raw_with_signal(_features(30, seed=18), seed=18)
    x, _ = build_xy(feat, raw)
    for col in _REAL_LEAK_COLUMNS:
        assert col not in x.columns
