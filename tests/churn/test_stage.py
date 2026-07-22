"""Integration tests for the real 03_train_churn stage (review High-1, Med).

Loads pipelines/03_train_churn.py by path (digit-led module name) and runs the
actual main() - the 1-3/1-4 lesson: function-level tests cannot catch stage
wiring regressions.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from crm.churn.artifact import artifact_id, model_meta_path, serialize_model
from crm.churn.model import ALL_PREDICTOR_COLUMNS, fit_and_compare
from crm.common.atomic import write_parquet_with_meta
from crm.common.freshness import build_meta


def _load_stage_03():
    path = Path(__file__).resolve().parents[2] / "pipelines" / "03_train_churn.py"
    spec = importlib.util.spec_from_file_location("stage_03_train_churn", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_inputs(tmp_path: Path, n: int = 120) -> tuple[Path, Path]:
    rng = np.random.default_rng(0)
    feat = pd.DataFrame({
        "CLIENTNUM": np.arange(n),
        "recency_proxy": rng.integers(0, 6, n),
        "frequency_proxy": rng.integers(10, 140, n),
        "monetary_proxy": rng.uniform(500, 18000, n),
        "segment_id": rng.integers(1, 5, n),
    })
    p_attr = 1 / (1 + np.exp((feat["frequency_proxy"].to_numpy() - 60) / 15))
    attr = rng.random(n) < p_attr
    raw = pd.DataFrame({
        "CLIENTNUM": feat["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": np.where(attr, "Attrited Customer", "Existing Customer"),
        "Total_Relationship_Count": rng.integers(1, 7, n),
        "Months_Inactive_12_mon": np.where(attr, rng.integers(2, 7, n), rng.integers(0, 4, n)),
        "Contacts_Count_12_mon": rng.integers(0, 7, n),
        "Total_Amt_Chng_Q4_Q1": rng.uniform(0.2, 2.0, n),
        "Total_Ct_Chng_Q4_Q1": rng.uniform(0.2, 2.0, n),
        "Avg_Utilization_Ratio": rng.uniform(0.0, 1.0, n),
    })
    feat_p = tmp_path / "features_customers.parquet"
    raw_p = tmp_path / "bankchurners.parquet"
    feat.to_parquet(feat_p, index=False)
    raw.to_parquet(raw_p, index=False)
    feat_p.with_suffix(feat_p.suffix + ".meta.json").write_text(
        json.dumps(build_meta("02_features", [], rows=n)), encoding="utf-8")
    raw_p.with_suffix(raw_p.suffix + ".meta.json").write_text(
        json.dumps(build_meta("01_download", [], rows=n)), encoding="utf-8")
    return feat_p, raw_p


def test_deleted_model_forces_a_rerun(tmp_path):
    # review High-1: with only the scored parquet checked for freshness, deleting
    # the model file made the stage skip forever. The gate must also require the
    # model to exist.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])
    assert model_p.exists() and scored_p.exists()

    model_p.unlink()  # lose the sibling artifact
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])
    assert model_p.exists(), "stage skipped as fresh with the model missing"


def test_stage_stamps_the_model_identity_onto_every_scored_row(tmp_path):
    # AD-5: the scores must be provably from THIS model, not merely alongside it.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    meta = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))
    scored = pd.read_parquet(scored_p)
    assert scored["artifact_id"].unique().tolist() == [meta["artifact_id"]]
    assert meta["artifact_id"] == artifact_id(model_p.read_bytes())
    assert meta["features"] and meta["random_seed"] == 42
    assert meta["metrics"]["xgboost_pr_auc"] > 0
    assert set(meta["inputs"]) == {"features_customers.parquet", "bankchurners.parquet"}


def test_tampered_scored_identity_forces_a_rerun(tmp_path):
    # The 1-6a crash window (new model + old scores) becomes self-healing: an
    # inconsistent pair reads as stale instead of being skipped as fresh.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    scored = pd.read_parquet(scored_p)
    scored["artifact_id"] = "0" * 64
    scored.to_parquet(scored_p, index=False)

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    restored = pd.read_parquet(scored_p)["artifact_id"].unique().tolist()
    assert restored == [artifact_id(model_p.read_bytes())], "stage skipped a mismatched pair"


def test_deleted_identity_record_forces_a_rerun(tmp_path):
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    model_meta_path(model_p).unlink()
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    assert model_meta_path(model_p).exists(), "stage skipped with no AD-5 record"


def test_replaced_model_bytes_force_a_rerun(tmp_path):
    # Review High: swap the model for a different valid one and leave the record
    # and the scores untouched. A record-only gate skips and the pipeline then
    # explains OLD probabilities with a NEW model.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])
    original = artifact_id(model_p.read_bytes())

    other = fit_and_compare(pd.read_parquet(feat_p), pd.read_parquet(raw_p), seed=7).model
    model_p.write_bytes(serialize_model(other))
    assert artifact_id(model_p.read_bytes()) != original

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    restored = artifact_id(model_p.read_bytes())
    meta = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))
    scored_ids = pd.read_parquet(scored_p)["artifact_id"].unique().tolist()
    assert restored == original, "stage skipped a swapped model"
    assert meta["artifact_id"] == restored == scored_ids[0]


def test_stage_records_the_seed_it_actually_trained_with(tmp_path, monkeypatch):
    # Review Med-1: the stage used to record config.RANDOM_SEED while letting
    # fit_and_compare fall back to its own captured default - a record that can
    # name a seed the model was never trained with.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    monkeypatch.setattr(stage.config, "RANDOM_SEED", 7)

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    meta = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))
    trained_with_7 = fit_and_compare(pd.read_parquet(feat_p), pd.read_parquet(raw_p), seed=7)
    assert meta["random_seed"] == 7
    # The identity covers the {model, calibrator} BUNDLE (story 3-0): hashing the
    # model alone would let the calibrator be swapped without the id moving.
    assert artifact_id(model_p.read_bytes()) == artifact_id(serialize_model(trained_with_7.bundle()))


def test_stage_skips_a_consistent_pair(tmp_path):
    # The gate must not rerun forever: an intact triple (model + record + scores)
    # is left exactly as it was.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])
    trained_at = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"]

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    assert json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"] == trained_at


def test_pre_3_0_schema_outputs_force_a_rerun(tmp_path):
    """The gate must not skip on outputs that are consistent but out of date.

    This is the story 3-0 migration itself: a scored file written before the
    column split is perfectly self-consistent - model, record and both derived
    files agree - and `crm/config.py` did not change, so nothing else in the
    freshness path has a reason to invalidate it. Identity records WHICH model
    wrote the outputs, never WHICH COLUMNS, so without a schema check the stage
    returns early and the retired `churn_prob` survives the upgrade.

    `data/` outputs are kept across branch switches in this repo, so this is the
    normal way to arrive here, not a contrived one.
    """
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])
    trained_at = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"]

    # Rewrite the scores under the OLD schema, keeping the identity stamp intact
    # so the only thing wrong is the column contract.
    scored = pd.read_parquet(scored_p)
    old = scored[["CLIENTNUM", "churn_score", "artifact_id"]].rename(
        columns={"churn_score": "churn_prob"}
    )
    meta = build_meta("03_train_churn", [feat_p, raw_p], rows=len(old))
    write_parquet_with_meta(scored_p, old, meta)

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    assert json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"] != trained_at
    assert "churn_prob" not in pd.read_parquet(scored_p).columns


def test_stage_output_is_deterministic_across_two_runs(tmp_path):
    # AD-7 acceptance as a REGRESSION TEST (review: the manual run log is not a
    # test). Two independent output paths, identical churn_score.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    out_a = (tmp_path / "a_model.joblib", tmp_path / "a_scored.parquet", tmp_path / "a_shap.parquet")
    out_b = (tmp_path / "b_model.joblib", tmp_path / "b_scored.parquet", tmp_path / "b_shap.parquet")
    stage.main([feat_p, raw_p], list(out_a))
    stage.main([feat_p, raw_p], list(out_b))
    a = pd.read_parquet(out_a[1]).sort_values("CLIENTNUM").reset_index(drop=True)
    b = pd.read_parquet(out_b[1]).sort_values("CLIENTNUM").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


# --- story 1-7: SHAP output is bound to the same training run ----------------

def test_stage_writes_shap_bound_to_the_same_artifact(tmp_path):
    # AD-5: churn_score and its explanation must be provably from one model.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    aid = artifact_id(model_p.read_bytes())
    shap_out = pd.read_parquet(shap_p)
    scored = pd.read_parquet(scored_p)
    assert shap_out["artifact_id"].unique().tolist() == [aid]
    assert shap_out["CLIENTNUM"].tolist() == scored["CLIENTNUM"].tolist()
    assert set(ALL_PREDICTOR_COLUMNS).issubset(shap_out.columns)
    assert shap_p.with_suffix(shap_p.suffix + ".meta.json").exists()  # AD-13


def test_deleted_shap_output_forces_a_rerun(tmp_path):
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    shap_p.unlink()
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    assert shap_p.exists(), "stage skipped with the SHAP output missing"


def test_tampered_shap_identity_forces_a_rerun(tmp_path):
    # A stale explanation next to fresh scores is the AD-5 failure mode, just
    # one output over from the one 1-6b closed.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    shap_p = tmp_path / "churn_shap.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    tampered = pd.read_parquet(shap_p)
    tampered["artifact_id"] = "0" * 64
    tampered.to_parquet(shap_p, index=False)

    stage.main([feat_p, raw_p], [model_p, scored_p, shap_p])

    assert pd.read_parquet(shap_p)["artifact_id"].unique().tolist() == [
        artifact_id(model_p.read_bytes())
    ], "stage skipped a mismatched explanation"


def test_shap_values_are_identical_across_two_stage_runs(tmp_path):
    # AC4 as a stage-level regression, not a function-level one.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    out_a = (tmp_path / "a_model.joblib", tmp_path / "a_scored.parquet", tmp_path / "a_shap.parquet")
    out_b = (tmp_path / "b_model.joblib", tmp_path / "b_scored.parquet", tmp_path / "b_shap.parquet")
    stage.main([feat_p, raw_p], list(out_a))
    stage.main([feat_p, raw_p], list(out_b))
    pd.testing.assert_frame_equal(pd.read_parquet(out_a[2]), pd.read_parquet(out_b[2]))
