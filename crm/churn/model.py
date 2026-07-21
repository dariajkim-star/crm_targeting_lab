"""Churn-risk classification: baseline logistic vs XGBoost (CAP-2, FR4/FR5).

Label nature (AD-6, NFR2). ``Attrition_Flag`` is a CROSS-SECTIONAL, after-the-fact
snapshot label, not a time-series outcome. Everything here is a CROSS-SECTIONAL
CHURN-RISK CLASSIFIER: there is no observation window, no prediction horizon, and
this module never frames the task as forecasting. That limitation is stated in
the report too.

Predictors (X) are the continuous RFM proxies from the feature table; the label
(y) comes from the raw frame and is kept STRICTLY separate from X - the model
never sees the target, nor the two Naive_Bayes_Classifier_* columns (which are
precomputed on the target and correlate +/-1.0 with it; feeding them scores a
meaningless AUC of 1.0). ``build_xy`` enforces both exclusions.

Determinism (AD-7). XGBoost gets ``random_state``, ``n_jobs=1`` and a pinned
``tree_method`` - with more than one thread the floating-point reduction order
drifts and probabilities wobble enough to move customers across a downstream
quantile boundary. Cross-validation folds are seeded. Two runs produce identical
probabilities.

Purity: functions do not read or write files; the pipeline layer owns I/O.
Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

from crm.config import CHURN_CV_FOLDS, CHURN_TREE_METHOD, RANDOM_SEED

__all__ = [
    "PREDICTOR_COLUMNS",
    "build_xy",
    "make_baseline",
    "make_xgboost",
    "pr_auc_cv",
    "lift",
    "score_customers",
    "fit_and_compare",
    "ChurnResult",
]

_ID_COLUMN = "CLIENTNUM"
_LABEL_COLUMN = "Attrition_Flag"
_POSITIVE_LABEL = "Attrited Customer"

# Continuous RFM proxies only. The R/F/M SCORES and segment_id are quantised or
# derived from these three, so including them adds redundancy, not signal.
PREDICTOR_COLUMNS = ("recency_proxy", "frequency_proxy", "monetary_proxy")

# Never allowed into X: the target itself and the target-correlated leakage pair.
_LEAKAGE_PREFIX = "Naive_Bayes_Classifier_"


def build_xy(features: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Assemble predictors X and cross-sectional label y, joined on CLIENTNUM.

    X is exactly ``PREDICTOR_COLUMNS`` (no target, no leakage columns); y is 1 for
    an attrited customer, 0 otherwise. Keys are validated (unique, non-null) so a
    duplicate/missing customer cannot silently misalign X and y.
    """
    for frame, name, needed in (
        (features, "features", (_ID_COLUMN, *PREDICTOR_COLUMNS)),
        (raw, "raw", (_ID_COLUMN, _LABEL_COLUMN)),
    ):
        missing = [c for c in needed if c not in frame.columns]
        if missing:
            raise KeyError(f"{name} frame is missing columns {missing}")
    for frame, name in ((features, "features"), (raw, "raw")):
        if frame[_ID_COLUMN].isna().any():
            raise ValueError(f"{name} CLIENTNUM must not contain nulls")
        if not frame[_ID_COLUMN].is_unique:
            raise ValueError(f"{name} CLIENTNUM must be unique (one row per customer)")

    merged = features[[_ID_COLUMN, *PREDICTOR_COLUMNS]].merge(
        raw[[_ID_COLUMN, _LABEL_COLUMN]], on=_ID_COLUMN, how="inner", validate="one_to_one"
    )
    if len(merged) != len(features):
        raise ValueError(
            f"X/y join lost rows ({len(features)} features -> {len(merged)} matched); "
            f"reconcile CLIENTNUM between features and raw."
        )
    # Defensive leakage re-audit (sprint-status warning): the target and the
    # Naive_Bayes_* columns must never reach X. They are not in PREDICTOR_COLUMNS,
    # but assert it so a future edit cannot smuggle one in.
    leaks = [c for c in PREDICTOR_COLUMNS if c == _LABEL_COLUMN or c.startswith(_LEAKAGE_PREFIX)]
    if leaks:
        raise ValueError(f"predictor set contains target/leakage columns: {leaks}")

    x = merged[list(PREDICTOR_COLUMNS)].set_axis(merged[_ID_COLUMN], axis=0)
    y = merged[_LABEL_COLUMN].eq(_POSITIVE_LABEL).astype(int).set_axis(merged[_ID_COLUMN], axis=0)
    return x, y


def make_baseline(y: pd.Series, seed: int = RANDOM_SEED) -> LogisticRegression:
    """Baseline: class-weighted logistic regression (handles the 16% imbalance)."""
    return LogisticRegression(
        class_weight="balanced", random_state=seed, max_iter=1000, solver="lbfgs"
    )


def make_xgboost(y: pd.Series, seed: int = RANDOM_SEED) -> XGBClassifier:
    """XGBoost with imbalance handling and determinism pinned (AD-7).

    ``scale_pos_weight`` = negatives / positives balances the loss; ``n_jobs=1``
    and a fixed ``tree_method`` keep the floating-point reduction order stable.
    """
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    scale_pos_weight = negatives / positives if positives else 1.0
    return XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=seed,
        n_jobs=1,
        tree_method=CHURN_TREE_METHOD,
        eval_metric="aucpr",
    )


def pr_auc_cv(
    make_estimator: Callable[[pd.Series, int], object],
    x: pd.DataFrame,
    y: pd.Series,
    seed: int = RANDOM_SEED,
    n_splits: int = CHURN_CV_FOLDS,
) -> float:
    """Mean PR-AUC (average precision) over seeded stratified CV folds.

    PR-AUC, not ROC-AUC, is the headline: with a 16% positive rate ROC-AUC
    flatters a model that barely beats the base rate. Both models see the SAME
    folds. Not tautological - this trains real folds and scores held-out data.
    """
    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    scores: list[float] = []
    for train_idx, test_idx in splitter.split(x, y):
        estimator = make_estimator(y.iloc[train_idx], seed)
        estimator.fit(x.iloc[train_idx], y.iloc[train_idx])
        proba = estimator.predict_proba(x.iloc[test_idx])[:, 1]
        scores.append(average_precision_score(y.iloc[test_idx], proba))
    return float(sum(scores) / len(scores))


def lift(baseline: float, model: float) -> float:
    """Relative lift of ``model`` over ``baseline`` (e.g. 0.15 == +15%).

    Reported, never used as a pass/fail gate - falling short of +15% is stated
    honestly, not treated as failure (AC2).
    """
    if baseline <= 0:
        raise ValueError("baseline PR-AUC must be positive to express a relative lift")
    return (model - baseline) / baseline


def score_customers(model: object, x: pd.DataFrame) -> pd.Series:
    """Cross-sectional churn-RISK probability per customer, indexed like ``x``."""
    proba = model.predict_proba(x)[:, 1]
    return pd.Series(proba, index=x.index, name="churn_prob")


@dataclass(frozen=True)
class ChurnResult:
    """Everything 03_train_churn needs: the scoring model, per-customer scores,
    and the CV comparison figures for the report."""

    model: XGBClassifier
    scored: pd.DataFrame  # CLIENTNUM + churn_prob
    baseline_pr_auc: float
    xgboost_pr_auc: float
    pr_auc_lift: float
    positive_rate: float


def fit_and_compare(features: pd.DataFrame, raw: pd.DataFrame, seed: int = RANDOM_SEED) -> ChurnResult:
    """Build X/y, CV-compare baseline vs XGBoost, then fit XGBoost on all data
    and score every customer. Deterministic given ``seed``."""
    x, y = build_xy(features, raw)
    baseline_auc = pr_auc_cv(lambda yy, s: make_baseline(yy, s), x, y, seed)
    xgb_auc = pr_auc_cv(lambda yy, s: make_xgboost(yy, s), x, y, seed)

    model = make_xgboost(y, seed)
    model.fit(x, y)
    scores = score_customers(model, x)
    scored = pd.DataFrame({_ID_COLUMN: x.index.to_numpy(), "churn_prob": scores.to_numpy()})
    return ChurnResult(
        model=model,
        scored=scored,
        baseline_pr_auc=baseline_auc,
        xgboost_pr_auc=xgb_auc,
        pr_auc_lift=lift(baseline_auc, xgb_auc),
        positive_rate=float(y.mean()),
    )
