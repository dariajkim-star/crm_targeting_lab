"""SHAP driver attribution for the churn-risk model (CAP-3, FR6/FR7).

WHAT SHAP ANSWERS HERE - and what it does not. These values explain what the
MODEL used to reach a score. They are not causal: "contacts in the last 12
months pushed this customer's risk up" means the model leaned on that column,
not that another phone call would cause churn. Every artifact derived from this
module has to carry that distinction, because the retention actions built on top
of it read like causal claims if nobody says otherwise (NFR1).

Label nature is unchanged (AD-6): this explains a CROSS-SECTIONAL risk
classification, never a forecast.

WHERE IT RUNS (AD-5). SHAP is computed in ``03_train_churn`` and nowhere else -
downstream stages read the stored values. Recomputing later would silently
produce explanations from a differently-fitted model even when "no retraining"
is nominally respected, which is why the stored frame carries the model's
``artifact_id``.

DETERMINISM (AD-7). The background sample is drawn with the project seed and the
explainer sees rows in a fixed order, so two runs produce identical values. The
interventional perturbation is the mode that needs a background distribution -
it is deliberate, not a default: ``tree_path_dependent`` would need no seed at
all, and the AC requires background sampling to receive ``RANDOM_SEED``.

Purity: nothing here reads or writes files; the pipeline layer owns I/O (AD-9).
Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from crm.churn.model import attach_artifact_id
from crm.config import DRIVER_TOP_N, RANDOM_SEED, SHAP_BACKGROUND_SIZE

__all__ = [
    "shap_frame",
    "build_shap_output",
    "global_importance",
    "segment_top_drivers",
]

_ID_COLUMN = "CLIENTNUM"
_SEGMENT_COLUMN = "segment_id"


def shap_frame(
    model: object,
    x: pd.DataFrame,
    seed: int = RANDOM_SEED,
    background_size: int = SHAP_BACKGROUND_SIZE,
) -> pd.DataFrame:
    """Per-customer SHAP values, one column per predictor, indexed like ``x``.

    The background sample is drawn with ``seed`` (AD-7) and capped at
    ``background_size`` rows - the interventional explainer is O(background x
    rows), so the full frame as its own background would be wasteful without
    changing the ranking it produces.

    Returns a frame whose columns are EXACTLY ``x``'s columns in ``x``'s order.
    Callers rank by these columns, and a reordering would silently reshuffle
    every driver table downstream.
    """
    if background_size < 1:
        raise ValueError("background_size must be >= 1")
    if x.empty:
        raise ValueError("cannot explain an empty predictor frame")

    # Sampling with replacement=False; when x is smaller than the cap, take x
    # itself rather than raising - a small run (tests, a tiny slice) is a
    # legitimate caller, not an error.
    background = x if len(x) <= background_size else x.sample(background_size, random_state=seed)
    # Pass an explicit masker rather than the raw frame: shap's Independent
    # masker silently subsamples to max_samples=100, so handing it 200 rows
    # would leave the config constant describing a background that was never
    # used ("Background dataset has 200 samples but max_samples=100" - observed
    # 2026-07-21). Whatever SHAP_BACKGROUND_SIZE says is what the explainer sees.
    masker = shap.maskers.Independent(background, max_samples=len(background))
    explainer = shap.TreeExplainer(model, data=masker, feature_perturbation="interventional")
    values = np.asarray(explainer.shap_values(x))

    # The contract is narrow ON PURPOSE: a binary XGBClassifier explained at raw
    # margin has ONE output, so shap returns (n_rows, n_features). Anything else
    # means the model is no longer what this module was written for.
    #
    # An earlier version accepted a 3-D result and took the last axis as the
    # positive class. That is fail-OPEN: nothing guarantees the last output is
    # the positive one, and picking wrong yields correctly-shaped numbers that
    # explain "this customer STAYS" while every driver table is labelled the
    # opposite. Silent and plausible beats loud and wrong only in the wrong
    # direction - so refuse instead. A multiclass or non-XGBoost model needs a
    # deliberate design (classes_ inspection, explicit positive index, per-output
    # additivity checks), not a guess made here.
    if values.ndim != 2 or values.shape != x.shape:
        raise ValueError(
            f"expected binary XGBoost raw SHAP values shaped {x.shape}, got "
            f"{values.shape} - this module explains a single-output binary model; "
            f"a multi-output model needs an explicit positive-class contract"
        )
    return pd.DataFrame(values, index=x.index, columns=list(x.columns))


def build_shap_output(
    model: object,
    x: pd.DataFrame,
    artifact_id: str,
    seed: int = RANDOM_SEED,
    background_size: int = SHAP_BACKGROUND_SIZE,
) -> pd.DataFrame:
    """Stage-ready SHAP frame: CLIENTNUM + one column per predictor + artifact_id.

    Assembling it here (rather than in the stage) keeps ``03_train_churn`` a
    wiring-only module: AD-9 allows it no helper of its own, so anything with
    steps in it belongs on this side of the boundary.
    """
    frame = shap_frame(model, x, seed=seed, background_size=background_size)
    return attach_artifact_id(frame.reset_index(), artifact_id)


def global_importance(shap_values: pd.DataFrame) -> pd.Series:
    """Global driver ranking: mean |SHAP| per predictor, descending.

    Magnitude, not signed effect - a feature that pushes some customers toward
    churn and others away still matters. Ties break on the feature NAME so the
    order cannot depend on column iteration (AD-7).
    """
    if shap_values.empty:
        raise ValueError("cannot rank drivers from an empty SHAP frame")
    magnitude = shap_values.abs().mean()
    ordered = sorted(magnitude.items(), key=lambda item: (-item[1], item[0]))
    return pd.Series(dict(ordered), name="mean_abs_shap")


def segment_top_drivers(
    shap_values: pd.DataFrame,
    segments: pd.Series,
    top_n: int = DRIVER_TOP_N,
) -> pd.DataFrame:
    """Top-N drivers per segment: (segment_id, rank, feature, mean_abs_shap).

    ``segments`` is the 1-4 stable ``segment_id`` per customer, READ not
    recomputed (AD-5/AD-9: clustering belongs to its own stage). It is aligned on
    the index rather than by position, because a positional zip between two
    frames from different stages is exactly how a "segment 3" table ends up
    describing segment 1.
    """
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    missing = shap_values.index.difference(segments.index)
    if len(missing) > 0:
        raise ValueError(
            f"{len(missing)} explained customers have no segment_id - "
            f"reconcile with 02_features before ranking drivers"
        )

    aligned = segments.reindex(shap_values.index)
    if aligned.isna().any():
        raise ValueError("segment_id must not be null for an explained customer")

    rows: list[dict[str, object]] = []
    for segment_id, group in shap_values.abs().groupby(aligned, sort=True):
        ranked = sorted(group.mean().items(), key=lambda item: (-item[1], item[0]))
        for rank, (feature, value) in enumerate(ranked[:top_n], start=1):
            rows.append({
                _SEGMENT_COLUMN: segment_id,
                "rank": rank,
                "feature": feature,
                "mean_abs_shap": float(value),
            })
    return pd.DataFrame(rows, columns=[_SEGMENT_COLUMN, "rank", "feature", "mean_abs_shap"])
