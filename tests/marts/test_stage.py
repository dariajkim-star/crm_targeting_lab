"""Integration tests for the real 05_marts stage (AC5, AC6, AC7).

Loads pipelines/05_marts.py by path (digit-led module name) and runs the actual
main(). Function-level tests in test_customers.py cover assembly and
serialization; only running the stage exercises the wiring the ACs name: the
AD-5 identity gate against a real model record (AC5), the atomic CSV + sibling
meta write (AC7), and byte-identical output across two runs (AC6).

Skips without xgboost: the gate consumes `crm.churn.artifact`, which imports the
churn model stack at module load. On an environment with the churn stack the
whole flow runs; without it, the stage cannot be exercised here (3-4 convention).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost", reason="the AD-5 gate imports the churn model stack")

from crm.churn.artifact import (  # noqa: E402 - after importorskip on purpose
    ArtifactIdentityError,
    artifact_id,
    build_model_meta,
    model_meta_path,
    serialize_model,
)
from crm.common.atomic import write_with_meta  # noqa: E402
from crm.common.freshness import meta_path_for  # noqa: E402


def _load_stage_05():
    path = Path(__file__).resolve().parents[2] / "pipelines" / "05_marts.py"
    spec = importlib.util.spec_from_file_location("stage_05_marts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_inputs(tmp_path: Path, n: int = 40) -> tuple[Path, Path, Path, Path, str]:
    """Three aligned sources plus a stub model whose id the scores carry.

    The model is a stub object: `read_verified_model_meta` compares the record's
    artifact_id to the file's own sha256, and `artifact_id` is defined as that
    hash - so a dummy payload with a matching record passes the gate without
    training anything. What the gate proves (scores describe the on-disk model)
    is exercised faithfully.
    """
    clientnums = np.arange(1000, 1000 + n)
    bankchurners = pd.DataFrame({"CLIENTNUM": clientnums, "Total_Trans_Amt": np.arange(500, 500 + n)})
    features = pd.DataFrame({"CLIENTNUM": clientnums, "segment_id": clientnums % 4})
    payload = serialize_model({"stub_model": 1})
    aid = artifact_id(payload)
    scored = pd.DataFrame(
        {
            "CLIENTNUM": clientnums,
            "churn_score": np.linspace(0.05, 0.9, n, dtype="float32"),
            "churn_prob_calibrated": np.linspace(0.05, 0.9, n),
            "artifact_id": aid,
        }
    )

    bc_p = tmp_path / "bankchurners.parquet"
    ft_p = tmp_path / "features_customers.parquet"
    sc_p = tmp_path / "churn_scored.parquet"
    model_p = tmp_path / "churn_model.joblib"
    bankchurners.to_parquet(bc_p, index=False)
    features.to_parquet(ft_p, index=False)
    scored.to_parquet(sc_p, index=False)
    write_with_meta(
        model_p,
        lambda tmp: tmp.write_bytes(payload),
        build_model_meta(payload, inputs=[], features=[], seed=42, metrics={}),
        meta_path=model_meta_path(model_p),
    )
    return bc_p, ft_p, sc_p, model_p, aid


def test_stage_writes_mart_and_meta_atomically(tmp_path):
    """AC7: a CSV output and its sibling <output>.meta.json land together."""
    stage = _load_stage_05()
    bc_p, ft_p, sc_p, model_p, _aid = _seed_inputs(tmp_path)
    mart_out = tmp_path / "mart_customers.csv"

    stage.main([bc_p, ft_p, sc_p, model_p], [mart_out])

    assert mart_out.exists()
    meta_file = meta_path_for(mart_out)
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["stage"] == "05_marts"
    assert meta["rows"] == 40
    assert set(meta["inputs"]) == {
        "bankchurners.parquet",
        "features_customers.parquet",
        "churn_scored.parquet",
    }
    assert "config_hash" in meta

    header = mart_out.read_bytes().decode("utf-8").split("\n", 1)[0]
    assert header == "CLIENTNUM,segment_id,customer_value,churn_score,churn_prob_calibrated,quadrant_official,threshold_official_risk,threshold_official_value,expected_saving,target_priority"


def test_stage_output_is_byte_identical_across_two_runs(tmp_path):
    """AC6: two consecutive runs produce a byte-identical mart CSV."""
    stage = _load_stage_05()
    bc_p, ft_p, sc_p, model_p, _aid = _seed_inputs(tmp_path)
    out_a = tmp_path / "a.csv"
    out_b = tmp_path / "b.csv"

    stage.main([bc_p, ft_p, sc_p, model_p], [out_a])
    stage.main([bc_p, ft_p, sc_p, model_p], [out_b])

    assert out_a.read_bytes() == out_b.read_bytes()


def test_stage_rejects_scores_from_a_foreign_model(tmp_path):
    """AC5: an artifact_id that does not match the model fails, not warns."""
    stage = _load_stage_05()
    bc_p, ft_p, sc_p, model_p, _aid = _seed_inputs(tmp_path)
    scored = pd.read_parquet(sc_p)
    scored["artifact_id"] = "0" * 64  # a valid-looking but foreign id
    scored.to_parquet(sc_p, index=False)
    mart_out = tmp_path / "mart_customers.csv"

    with pytest.raises(ArtifactIdentityError):
        stage.main([bc_p, ft_p, sc_p, model_p], [mart_out])

    assert not mart_out.exists(), "no mart may be written when the identity gate fails"
