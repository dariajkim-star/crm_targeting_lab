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

from crm.churn.artifact import artifact_id, model_meta_path
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
    })
    p_attr = 1 / (1 + np.exp((feat["frequency_proxy"].to_numpy() - 60) / 15))
    raw = pd.DataFrame({
        "CLIENTNUM": feat["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": np.where(rng.random(n) < p_attr,
                                   "Attrited Customer", "Existing Customer"),
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

    stage.main([feat_p, raw_p], [model_p, scored_p])
    assert model_p.exists() and scored_p.exists()

    model_p.unlink()  # lose the sibling artifact
    stage.main([feat_p, raw_p], [model_p, scored_p])
    assert model_p.exists(), "stage skipped as fresh with the model missing"


def test_stage_stamps_the_model_identity_onto_every_scored_row(tmp_path):
    # AD-5: the scores must be provably from THIS model, not merely alongside it.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"

    stage.main([feat_p, raw_p], [model_p, scored_p])

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
    stage.main([feat_p, raw_p], [model_p, scored_p])

    scored = pd.read_parquet(scored_p)
    scored["artifact_id"] = "0" * 64
    scored.to_parquet(scored_p, index=False)

    stage.main([feat_p, raw_p], [model_p, scored_p])

    restored = pd.read_parquet(scored_p)["artifact_id"].unique().tolist()
    assert restored == [artifact_id(model_p.read_bytes())], "stage skipped a mismatched pair"


def test_deleted_identity_record_forces_a_rerun(tmp_path):
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p])

    model_meta_path(model_p).unlink()
    stage.main([feat_p, raw_p], [model_p, scored_p])

    assert model_meta_path(model_p).exists(), "stage skipped with no AD-5 record"


def test_stage_skips_a_consistent_pair(tmp_path):
    # The gate must not rerun forever: an intact triple (model + record + scores)
    # is left exactly as it was.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    stage.main([feat_p, raw_p], [model_p, scored_p])
    trained_at = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"]

    stage.main([feat_p, raw_p], [model_p, scored_p])

    assert json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))["trained_at"] == trained_at


def test_stage_output_is_deterministic_across_two_runs(tmp_path):
    # AD-7 acceptance as a REGRESSION TEST (review: the manual run log is not a
    # test). Two independent output paths, identical churn_prob.
    stage = _load_stage_03()
    feat_p, raw_p = _seed_inputs(tmp_path)
    out_a = (tmp_path / "a_model.joblib", tmp_path / "a_scored.parquet")
    out_b = (tmp_path / "b_model.joblib", tmp_path / "b_scored.parquet")
    stage.main([feat_p, raw_p], list(out_a))
    stage.main([feat_p, raw_p], list(out_b))
    a = pd.read_parquet(out_a[1]).sort_values("CLIENTNUM").reset_index(drop=True)
    b = pd.read_parquet(out_b[1]).sort_values("CLIENTNUM").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
