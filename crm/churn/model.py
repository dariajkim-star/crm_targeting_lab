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

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from crm.config import CHURN_CV_FOLDS, CHURN_TREE_METHOD, RANDOM_SEED

__all__ = [
    "PREDICTOR_COLUMNS",
    "RAW_PREDICTOR_COLUMNS",
    "ALL_PREDICTOR_COLUMNS",
    "build_xy",
    "make_baseline",
    "make_xgboost",
    "pr_auc_cv",
    "lift",
    "score_customers",
    "attach_artifact_id",
    "fit_and_compare",
    "ChurnResult",
]

_ID_COLUMN = "CLIENTNUM"
_LABEL_COLUMN = "Attrition_Flag"
_POSITIVE_LABEL = "Attrited Customer"
# The label's full vocabulary. Anything else - a typo, trailing whitespace,
# "Unknown", null, a parser artefact - is REJECTED rather than silently scored
# as an existing customer (review High-2: `.eq(positive)` mapped every anomaly
# to 0). Failing beats silently corrupting the training population.
_ALLOWED_LABELS = frozenset({"Attrited Customer", "Existing Customer"})

# Continuous RFM proxies from the FEATURE table. The R/F/M SCORES and segment_id
# are quantised or derived from these three, so including them adds redundancy.
PREDICTOR_COLUMNS = ("recency_proxy", "frequency_proxy", "monetary_proxy")

# Churn-signal predictors taken from the RAW frame (story 1-7).
#
# WHY THESE EXIST. Story 1-6a trained on the three RFM proxies alone, because it
# reused the table built for SEGMENTATION (CAP-1). That is inherited, not
# designed: an explanation built on those three can only ever say "spend fell,
# so churn risk is high", which restates the definition instead of naming a
# cause an operator can act on. CAP-3 asks for drivers that translate into
# retention actions, and that needs signals the RFM axes do not carry.
#
# WHY FROM THE RAW FRAME. ``build_xy`` already receives it (for the label), so
# widening X here leaves ``features_customers`` untouched - which means the
# 1-4 K-means segments and the 1-5 personas built on them do NOT move. Adding
# these columns to the feature table instead would change the clustering input
# and silently renumber every segment.
#
# WHY Avg_Utilization_Ratio IS ALLOWED HERE. SPEC CAP-5 bars it from the
# customer VALUE axis - it is a profiling-only reference indicator, never summed
# into value - and CAP-5 was amended (2026-07-21) to state explicitly that use
# as a churn-risk PREDICTOR is a separate question that the value ban does not
# cover. It must never be read back as a value signal, and never as causal
# evidence for an action.
#
# NOT INCLUDED, deliberately:
#   - Months_Inactive_12_mon: recency_proxy IS this column verbatim (story 1-3
#     defines the recency proxy as Months_Inactive_12_mon unchanged) - measured
#     2026-07-21: byte-identical per customer, and with both present XGBoost
#     used one and SHAP-zeroed the other, which would read as "inactivity does
#     not matter" in the driver tables. Exact duplicates explain nothing.
#   - Credit_Limit: ABLATION-TESTED and dropped (2026-07-21). Including it moved
#     XGBoost PR-AUC by +0.005 (0.9508 -> 0.9559), ranked it LAST of nine drivers
#     (mean |SHAP| 0.287) and put it in one segment's top-5 out of four. The
#     limit-frustration persona SPEC CAP-3 imagines is not in this data either
#     (utilisation correlates NEGATIVELY with risk). A column that buys 0.005 and
#     invites a value-axis argument is not worth carrying.
#   - Avg_Open_To_Buy (= Credit_Limit - Total_Revolving_Bal, fully redundant).
#   - The five categorical columns (Gender / Education_Level / Income_Category /
#     Marital_Status / Card_Category) - those need the fixed lexicographic
#     encoding AD-7 mandates, and a demographic driver does not translate into a
#     retention action ("being 30 is why they churn" buys nothing).
# See deferred-work.md.
RAW_PREDICTOR_COLUMNS = (
    "Total_Relationship_Count",
    "Contacts_Count_12_mon",
    "Total_Amt_Chng_Q4_Q1",
    "Total_Ct_Chng_Q4_Q1",
    "Avg_Utilization_Ratio",
)

# The full predictor set, in a FIXED order (AD-7: column order must not depend on
# dict iteration or merge order, or SHAP columns shuffle between runs).
ALL_PREDICTOR_COLUMNS = PREDICTOR_COLUMNS + RAW_PREDICTOR_COLUMNS

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
        (raw, "raw", (_ID_COLUMN, _LABEL_COLUMN, *RAW_PREDICTOR_COLUMNS)),
    ):
        missing = [c for c in needed if c not in frame.columns]
        if missing:
            raise KeyError(f"{name} frame is missing columns {missing}")
    for frame, name in ((features, "features"), (raw, "raw")):
        if frame[_ID_COLUMN].isna().any():
            raise ValueError(f"{name} CLIENTNUM must not contain nulls")
        if not frame[_ID_COLUMN].is_unique:
            raise ValueError(f"{name} CLIENTNUM must be unique (one row per customer)")

    # BOTH directions of key mismatch are defects (review High-3): a features-only
    # customer has no label, and a raw-only customer means the feature stage
    # silently dropped someone - either way the training population is corrupted.
    feature_ids = set(features[_ID_COLUMN])
    raw_ids = set(raw[_ID_COLUMN])
    if feature_ids != raw_ids:
        raise ValueError(
            f"CLIENTNUM sets differ between features and raw: "
            f"{len(raw_ids - feature_ids)} customers lack features, "
            f"{len(feature_ids - raw_ids)} lack labels. Reconcile upstream."
        )

    # Explicit column WHITELIST on both sides. Now that predictors come from the
    # raw frame too, a wildcard/"everything else" selection would eventually drag
    # the target or the Naive_Bayes_* pair into X - the exact leak this project
    # was warned about. Name every column that is allowed through.
    merged = features[[_ID_COLUMN, *PREDICTOR_COLUMNS]].merge(
        raw[[_ID_COLUMN, _LABEL_COLUMN, *RAW_PREDICTOR_COLUMNS]],
        on=_ID_COLUMN, how="inner", validate="one_to_one",
    )
    # Canonical row order (review Med-7): StratifiedKFold splits by POSITION, so
    # without a fixed order the same customers land in different folds when the
    # caller's row order changes - and the reported CV numbers drift with it.
    merged = merged.sort_values(_ID_COLUMN, kind="mergesort").reset_index(drop=True)

    # Label vocabulary check (review High-2): fail on nulls and unknown values
    # instead of silently scoring them as existing customers.
    if merged[_LABEL_COLUMN].isna().any():
        raise ValueError(f"{_LABEL_COLUMN} must not contain nulls")
    unknown = set(merged[_LABEL_COLUMN].unique()) - _ALLOWED_LABELS
    if unknown:
        raise ValueError(f"unexpected {_LABEL_COLUMN} values: {sorted(unknown)}")

    # Defensive leakage re-audit (sprint-status warning). Since 1-7 pulls
    # predictors OUT OF THE RAW FRAME, this assertion stopped being theoretical:
    # the target and the Naive_Bayes_* pair (correlated +/-1.0 with it) live in
    # that same frame, one typo away from X.
    leaks = [c for c in ALL_PREDICTOR_COLUMNS
             if c == _LABEL_COLUMN or c.startswith(_LEAKAGE_PREFIX)]
    if leaks:
        raise ValueError(f"predictor set contains target/leakage columns: {leaks}")

    x = merged[list(ALL_PREDICTOR_COLUMNS)].set_axis(merged[_ID_COLUMN], axis=0)
    # Predictors must be finite numerics for BOTH models (review Low-10): XGBoost
    # tolerates NaN but the logistic baseline does not, and a cryptic sklearn
    # error far from here would hide the real data defect.
    if not all(pd.api.types.is_numeric_dtype(x[c]) for c in ALL_PREDICTOR_COLUMNS):
        raise TypeError(f"predictors must be numeric: {list(ALL_PREDICTOR_COLUMNS)}")
    if not np.isfinite(x.to_numpy(dtype=float)).all():
        raise ValueError("predictors contain NaN/inf - clean upstream before training")
    y = merged[_LABEL_COLUMN].eq(_POSITIVE_LABEL).astype(int).set_axis(merged[_ID_COLUMN], axis=0)
    return x, y


def make_baseline(y: pd.Series, seed: int = RANDOM_SEED) -> Pipeline:
    """Baseline: standardised, class-weighted logistic regression.

    StandardScaler first (review Med-5): L2-regularised logistic regression is
    NOT scale-invariant, and monetary spans thousands while recency spans single
    digits - an unscaled baseline would be artificially weak and inflate the
    reported lift. (On the real data the scaled and unscaled baselines happen to
    score identically to 4 decimals, but the comparison must not depend on that
    accident.)
    """
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", random_state=seed, max_iter=1000, solver="lbfgs"),
    )


def make_xgboost(y: pd.Series, seed: int = RANDOM_SEED) -> XGBClassifier:
    """XGBoost with imbalance handling and determinism pinned (AD-7).

    ``scale_pos_weight`` = negatives / positives balances the loss; ``n_jobs=1``
    and a fixed ``tree_method`` keep the floating-point reduction order stable.

    ``enable_categorical=False`` is explicit rather than incidental (story 1-7):
    X is all-numeric by contract (``build_xy`` rejects anything else), and
    xgboost 3.3 leaves the flag ON by default - which makes shap 0.52 refuse the
    interventional TreeExplainer outright ("Categorical split is not yet
    supported"), whether or not a categorical feature exists. Turning it off
    states the truth about X and is what lets SHAP use a background sample.
    Measured: predictions are bit-identical with the flag off.
    """
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0 or negatives == 0:
        # A single-class y would surface later as a cryptic XGBoost/sklearn error
        # (review Med-4); name the real problem here.
        raise ValueError("y must contain both classes (0 and 1) to train a classifier")
    scale_pos_weight = negatives / positives
    return XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=seed,
        n_jobs=1,
        tree_method=CHURN_TREE_METHOD,
        enable_categorical=False,
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
    # CV validity (review Med-4): both classes must exist and the minority class
    # must cover every fold, or some folds carry zero positives and the averaged
    # PR-AUC is meaningless.
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    counts = y.value_counts()
    if set(counts.index) != {0, 1}:
        raise ValueError("y must contain both classes 0 and 1 for stratified CV")
    if int(counts.min()) < n_splits:
        raise ValueError(
            f"minority class count {int(counts.min())} is below n_splits={n_splits}"
        )

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
    """Cross-sectional churn-RISK score per customer, indexed like ``x``.

    HONESTY (review Med-6): the column is named ``churn_prob`` because the
    architecture spine (AD-5, pipeline diagram) fixes that name, but the value is
    an UNCALIBRATED, IN-SAMPLE risk score: the final model is fit on all
    customers and scores those same customers, and ``scale_pos_weight`` reweights
    the loss so ``predict_proba`` does not track the true attrition rate.
    Treat it as a RANKING signal (who is riskier than whom), not a calibrated
    probability. Calibration is out of scope here and stated in the report.
    """
    proba = model.predict_proba(x)[:, 1]
    return pd.Series(proba, index=x.index, name="churn_prob")


def attach_artifact_id(scored: pd.DataFrame, artifact_id: str) -> pd.DataFrame:
    """Stamp the training run's identity onto every scored row (AD-5).

    Returns a NEW frame; the input is left untouched. An empty or non-string id
    is refused rather than written: a blank stamp looks like provenance while
    proving nothing, which is worse than no column at all.
    """
    if not isinstance(artifact_id, str):
        raise TypeError(f"artifact_id must be a string, got {type(artifact_id).__name__}")
    if not artifact_id:
        raise ValueError("artifact_id must not be empty - it is the proof of provenance")
    return scored.assign(artifact_id=artifact_id)


@dataclass(frozen=True)
class ChurnResult:
    """Everything 03_train_churn needs: the scoring model, per-customer scores,
    and the CV comparison figures for the report."""

    model: XGBClassifier
    scored: pd.DataFrame  # CLIENTNUM + churn_prob
    x: pd.DataFrame  # the predictors the model was fit on, CLIENTNUM-indexed:
    # SHAP must explain THESE rows in THIS order, and rebuilding them in the
    # stage would risk explaining a differently-assembled X than was scored.
    baseline_pr_auc: float
    xgboost_pr_auc: float
    pr_auc_lift: float
    positive_rate: float

    def metrics(self) -> dict[str, float]:
        """The comparison figures as a machine-readable record (AD-5 meta).

        Without this the baseline/XGBoost comparison exists only in a stage log
        line and a hand-copied report table - which is how a report and the
        artifact it describes drift apart unnoticed.
        """
        return {
            "baseline_pr_auc": self.baseline_pr_auc,
            "xgboost_pr_auc": self.xgboost_pr_auc,
            "pr_auc_lift": self.pr_auc_lift,
            "positive_rate": self.positive_rate,
            "cv_folds": float(CHURN_CV_FOLDS),
        }


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
        x=x,
        baseline_pr_auc=baseline_auc,
        xgboost_pr_auc=xgb_auc,
        pr_auc_lift=lift(baseline_auc, xgb_auc),
        positive_rate=float(y.mean()),
    )
