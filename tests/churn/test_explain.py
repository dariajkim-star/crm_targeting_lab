"""SHAP driver tests (story 1-7: AC1, AC3, AC4).

Properties pinned here: the explainer receives the seed and produces identical
values twice (AD-7), the values satisfy TreeExplainer's additivity identity
against the model's own margin (an oracle the implementation cannot fake by
calling shap again), any multi-output SHAP shape is refused rather than guessed
at (the 2-D binary-raw contract), and per-segment rankings are aligned by
CLIENTNUM rather than by row position.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import shap

from crm.churn.explain import (
    build_shap_output,
    global_importance,
    segment_top_drivers,
    shap_frame,
)
from crm.churn.model import ALL_PREDICTOR_COLUMNS, build_xy, fit_and_compare
from crm.config import DRIVER_TOP_N, RANDOM_SEED


def _frames(n: int = 200, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    features = pd.DataFrame({
        "CLIENTNUM": np.arange(n),
        "recency_proxy": rng.integers(0, 6, n),
        "frequency_proxy": rng.integers(10, 140, n),
        "monetary_proxy": rng.uniform(500, 18000, n),
        "segment_id": rng.integers(1, 5, n),
    })
    p_attr = 1 / (1 + np.exp((features["frequency_proxy"].to_numpy() - 60) / 15))
    attr = rng.random(n) < p_attr
    raw = pd.DataFrame({
        "CLIENTNUM": features["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": np.where(attr, "Attrited Customer", "Existing Customer"),
        "Total_Relationship_Count": rng.integers(1, 7, n),
        "Months_Inactive_12_mon": np.where(attr, rng.integers(2, 7, n), rng.integers(0, 4, n)),
        "Contacts_Count_12_mon": rng.integers(0, 7, n),
        "Total_Amt_Chng_Q4_Q1": rng.uniform(0.2, 2.0, n),
        "Total_Ct_Chng_Q4_Q1": rng.uniform(0.2, 2.0, n),
        "Avg_Utilization_Ratio": rng.uniform(0.0, 1.0, n),
    })
    return features, raw


def _fitted():
    features, raw = _frames()
    result = fit_and_compare(features, raw)
    return result, features


# --- AC4: determinism ---------------------------------------------------------


def test_shap_values_are_identical_across_two_runs():
    result, _ = _fitted()
    first = shap_frame(result.model, result.x)
    second = shap_frame(result.model, result.x)
    pd.testing.assert_frame_equal(first, second)


def test_background_sampling_actually_receives_the_seed(monkeypatch):
    # A background drawn without the seed would still "work" and still look
    # deterministic inside one process. Capture the sample and prove two
    # different seeds pick different reference rows.
    result, _ = _fitted()
    seen: list[pd.DataFrame] = []
    real = shap.TreeExplainer

    def _spy(model, data=None, **kwargs):
        # data is a shap masker; its .data holds the background rows verbatim
        # (the masker exists so shap does not subsample them behind our back).
        seen.append(pd.DataFrame(np.asarray(data.data)).copy())
        assert kwargs.get("feature_perturbation") == "interventional"
        return real(model, data=data, **kwargs)

    monkeypatch.setattr(shap, "TreeExplainer", _spy)
    shap_frame(result.model, result.x, seed=RANDOM_SEED, background_size=50)
    shap_frame(result.model, result.x, seed=RANDOM_SEED, background_size=50)
    shap_frame(result.model, result.x, seed=7, background_size=50)

    assert len(seen) == 3 and len(seen[0]) == 50
    # REPRODUCIBILITY is the property that pins the seed: dropping random_state
    # entirely would still make two DIFFERENT seeds disagree, so "they differ"
    # alone proves nothing (mutation-tested 2026-07-21).
    assert seen[0].equals(seen[1]), "same seed drew a different background"
    assert not seen[0].equals(seen[2]), "background ignored the seed"


def test_background_falls_back_to_the_whole_frame_when_smaller_than_the_cap():
    result, _ = _fitted()
    small = result.x.head(10)
    frame = shap_frame(result.model, small, background_size=500)
    assert len(frame) == 10


# --- AC1: the values are real SHAP values (oracle, not a re-call) -------------


def test_values_satisfy_the_additivity_identity_against_the_model_margin():
    # base_value + sum(shap) == raw margin. This is TreeExplainer's defining
    # property; an implementation returning the wrong class axis, a transposed
    # matrix or plain feature values fails it.
    result, _ = _fitted()
    frame = shap_frame(result.model, result.x)
    background = result.x.sample(200, random_state=RANDOM_SEED) if len(result.x) > 200 else result.x
    masker = shap.maskers.Independent(background, max_samples=len(background))
    explainer = shap.TreeExplainer(result.model, data=masker,
                                   feature_perturbation="interventional")
    expected_base = float(np.asarray(explainer.expected_value).ravel()[-1])
    margin = result.model.predict(result.x, output_margin=True)
    assert np.abs(expected_base + frame.to_numpy().sum(axis=1) - margin).max() < 1e-3


def test_explains_the_positive_class_not_the_negative_one():
    # Sanity anchor: customers the model scores as high risk must carry a larger
    # total positive contribution than the ones it scores as safe. If the wrong
    # class axis were picked, the relationship inverts.
    result, _ = _fitted()
    frame = shap_frame(result.model, result.x)
    # The FINAL model's own scores, not the persisted out-of-fold column: this
    # test checks that `shap_frame` explains `result.model`, so the ordering it
    # is checked against must come from that same model (story 3-0 split the
    # two - the persisted `churn_score` is produced by the fold models).
    scores = pd.Series(result.model.predict_proba(result.x)[:, 1], index=result.x.index)
    riskiest = scores.nlargest(30).index
    safest = scores.nsmallest(30).index
    risky_push = frame.loc[riskiest].to_numpy().sum(axis=1).mean()
    safe_push = frame.loc[safest].to_numpy().sum(axis=1).mean()
    assert risky_push > safe_push


def test_shape_and_columns_match_the_predictor_frame():
    result, _ = _fitted()
    frame = shap_frame(result.model, result.x)
    assert list(frame.columns) == list(ALL_PREDICTOR_COLUMNS)
    assert frame.index.equals(result.x.index)


def test_empty_predictor_frame_is_rejected():
    result, _ = _fitted()
    with pytest.raises(ValueError, match="empty"):
        shap_frame(result.model, result.x.head(0))


# --- AC1/AC2: stage-ready output ---------------------------------------------


def test_build_shap_output_carries_clientnum_and_the_artifact_id():
    result, _ = _fitted()
    out = build_shap_output(result.model, result.x, "a" * 64)
    assert list(out.columns) == ["CLIENTNUM"] + list(ALL_PREDICTOR_COLUMNS) + ["artifact_id"]
    assert out["artifact_id"].unique().tolist() == ["a" * 64]
    assert out["CLIENTNUM"].tolist() == result.x.index.tolist()


# --- AC3: global + per-segment rankings --------------------------------------


def test_global_importance_ranks_by_mean_absolute_shap():
    # Hardcoded oracle: column B has the larger average magnitude, and the sign
    # must not matter (a mean of signed values would rank A first).
    frame = pd.DataFrame({"a": [1.0, 1.0, 1.0], "b": [-4.0, 4.0, -4.0]})
    ranked = global_importance(frame)
    assert ranked.index.tolist() == ["b", "a"]
    assert ranked["b"] == pytest.approx(4.0)


def test_global_importance_breaks_ties_on_the_feature_name():
    frame = pd.DataFrame({"zeta": [1.0, -1.0], "alpha": [1.0, -1.0]})
    assert global_importance(frame).index.tolist() == ["alpha", "zeta"]


def test_segment_top_drivers_ranks_within_each_segment():
    shap_values = pd.DataFrame(
        {"a": [5.0, 5.0, 0.1, 0.1], "b": [0.1, 0.1, 5.0, 5.0], "c": [1.0, 1.0, 1.0, 1.0]},
        index=pd.Index([11, 12, 13, 14], name="CLIENTNUM"),
    )
    segments = pd.Series([1, 1, 2, 2], index=shap_values.index, name="segment_id")
    table = segment_top_drivers(shap_values, segments, top_n=2)

    seg1 = table[table["segment_id"] == 1]["feature"].tolist()
    seg2 = table[table["segment_id"] == 2]["feature"].tolist()
    assert seg1 == ["a", "c"]
    assert seg2 == ["b", "c"]
    assert table["rank"].tolist() == [1, 2, 1, 2]


def test_segment_top_drivers_aligns_on_clientnum_not_row_position():
    # The two frames come from different stages; a positional zip is how a
    # "segment 2" table ends up describing segment 1's customers.
    shap_values = pd.DataFrame(
        {"a": [9.0, 0.0], "b": [0.0, 9.0]},
        index=pd.Index([100, 200], name="CLIENTNUM"),
    )
    shuffled = pd.Series([2, 1], index=pd.Index([200, 100], name="CLIENTNUM"), name="segment_id")
    table = segment_top_drivers(shap_values, shuffled, top_n=1)
    assert table[table["segment_id"] == 1]["feature"].tolist() == ["a"]
    assert table[table["segment_id"] == 2]["feature"].tolist() == ["b"]


def test_segment_top_drivers_rejects_customers_without_a_segment():
    shap_values = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.Index([1, 2], name="CLIENTNUM"))
    partial = pd.Series([1], index=pd.Index([1], name="CLIENTNUM"))
    with pytest.raises(ValueError, match="no segment_id"):
        segment_top_drivers(shap_values, partial)


def test_segment_top_drivers_uses_the_configured_top_n_by_default():
    result, features = _fitted()
    frame = shap_frame(result.model, result.x)
    segments = features.set_index("CLIENTNUM")["segment_id"]
    table = segment_top_drivers(frame, segments)
    per_segment = table.groupby("segment_id").size().unique().tolist()
    assert per_segment == [DRIVER_TOP_N]


def test_multi_output_shap_is_refused_not_guessed(monkeypatch):
    # Review 7: an earlier version accepted (n, features, 2) and took the LAST
    # axis as the positive class. With outputs ordered [positive, negative] that
    # returns correctly-shaped numbers explaining "this customer STAYS" - worse
    # than a crash, because every driver table stays plausible. The contract is
    # now: binary XGBoost raw margin is 2-D; anything else fails fast.
    result, _ = _fitted()

    class _FakeExplainer:
        def __init__(self, *args, **kwargs):
            pass

        def shap_values(self, x):
            return np.zeros((len(x), x.shape[1], 2))  # [positive, negative]

    monkeypatch.setattr(shap, "TreeExplainer", _FakeExplainer)
    with pytest.raises(ValueError, match="single-output binary"):
        shap_frame(result.model, result.x)
