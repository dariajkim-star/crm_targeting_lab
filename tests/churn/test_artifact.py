"""Artifact identity tests (story 1-6b, AD-5).

The identity contract these lock down:
  - artifact_id is the SHA-256 of the MODEL BYTES (a definition later stories
    must not have to guess),
  - churn_model.meta.json carries the AD-5 fields with real (not hardcoded)
    library versions,
  - the scored frame carries the SAME id, and a mismatch RAISES rather than
    warns,
  - a failed meta write leaves the previous artifact intact.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crm.churn.artifact import (
    ArtifactIdentityError,
    artifact_id,
    build_model_meta,
    identity_is_consistent,
    model_meta_path,
    read_model_meta,
    save_model_with_identity,
    serialize_model,
    verify_artifact_identity,
)
from crm.churn.model import PREDICTOR_COLUMNS, attach_artifact_id, fit_and_compare


def _frames(n: int = 200, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    features = pd.DataFrame({
        "CLIENTNUM": np.arange(n),
        "recency_proxy": rng.integers(0, 6, n),
        "frequency_proxy": rng.integers(10, 140, n),
        "monetary_proxy": rng.uniform(500, 18000, n),
    })
    p_attr = 1 / (1 + np.exp((features["frequency_proxy"].to_numpy() - 60) / 15))
    raw = pd.DataFrame({
        "CLIENTNUM": features["CLIENTNUM"].to_numpy(),
        "Attrition_Flag": np.where(rng.random(n) < p_attr, "Attrited Customer", "Existing Customer"),
    })
    return features, raw


def _input_files(tmp_path: Path, features: pd.DataFrame, raw: pd.DataFrame) -> list[Path]:
    feat_p = tmp_path / "features_customers.parquet"
    raw_p = tmp_path / "bankchurners.parquet"
    features.to_parquet(feat_p, index=False)
    raw.to_parquet(raw_p, index=False)
    return [feat_p, raw_p]


# --- artifact_id definition ---------------------------------------------------


def test_artifact_id_is_the_sha256_of_the_model_bytes():
    # Hardcoded oracle: the definition itself, not a re-implementation.
    payload = b"model-bytes"
    assert artifact_id(payload) == hashlib.sha256(payload).hexdigest()


def test_artifact_id_is_identical_for_two_fits_with_the_same_seed_and_data():
    features, raw = _frames()
    first = artifact_id(serialize_model(fit_and_compare(features, raw).model))
    second = artifact_id(serialize_model(fit_and_compare(features, raw).model))
    assert first == second


def test_artifact_id_changes_with_the_seed():
    features, raw = _frames()
    base = artifact_id(serialize_model(fit_and_compare(features, raw, seed=42).model))
    other = artifact_id(serialize_model(fit_and_compare(features, raw, seed=7).model))
    assert base != other


def test_artifact_id_changes_when_the_training_data_changes():
    features, raw = _frames()
    base = artifact_id(serialize_model(fit_and_compare(features, raw).model))
    shifted = features.copy()
    shifted["monetary_proxy"] = shifted["monetary_proxy"] * 2.0
    assert base != artifact_id(serialize_model(fit_and_compare(shifted, raw).model))


# --- meta.json ----------------------------------------------------------------


def test_model_meta_path_is_the_ad5_name_not_the_ad13_sibling(tmp_path):
    # AD-5 names models/churn_model.meta.json. The AD-13 freshness sibling would
    # be churn_model.joblib.meta.json - a DIFFERENT file, and conflating them
    # would let a freshness record masquerade as an identity record.
    assert model_meta_path(tmp_path / "churn_model.joblib").name == "churn_model.meta.json"


def test_build_model_meta_records_every_ad5_field(tmp_path):
    features, raw = _frames()
    inputs = _input_files(tmp_path, features, raw)
    payload = b"model-bytes"
    meta = build_model_meta(
        payload, inputs=inputs, features=PREDICTOR_COLUMNS, seed=42,
        metrics={"baseline_pr_auc": 0.4, "xgboost_pr_auc": 0.8},
    )

    assert meta["artifact_id"] == artifact_id(payload)
    assert meta["random_seed"] == 42
    assert meta["features"] == list(PREDICTOR_COLUMNS)
    assert set(meta["inputs"]) == {"features_customers.parquet", "bankchurners.parquet"}
    assert all(len(h) == 64 for h in meta["inputs"].values())
    assert meta["trained_at"].endswith("+00:00")  # UTC, not naive local time
    assert meta["metrics"]["xgboost_pr_auc"] == 0.8


def test_meta_library_versions_are_read_from_the_environment(tmp_path):
    # A hardcoded version table would make the record a lie the moment the
    # environment moves. Compare against importlib.metadata, not a literal.
    inputs = _input_files(tmp_path, *_frames())
    meta = build_model_meta(b"x", inputs=inputs, features=PREDICTOR_COLUMNS, seed=42, metrics={})
    libraries = meta["libraries"]
    for package in ("xgboost", "scikit-learn", "joblib", "numpy", "pandas"):
        assert libraries[package] == version(package)
    assert libraries["python"].count(".") == 2


def test_metrics_do_not_participate_in_the_artifact_id(tmp_path):
    # Metrics ride ALONG with the identity; they are not part of it. Otherwise
    # the same model would get two ids across a metric-only change.
    inputs = _input_files(tmp_path, *_frames())
    common = dict(inputs=inputs, features=PREDICTOR_COLUMNS, seed=42)
    a = build_model_meta(b"same-bytes", metrics={"xgboost_pr_auc": 0.80}, **common)
    b = build_model_meta(b"same-bytes", metrics={"xgboost_pr_auc": 0.99}, **common)
    assert a["artifact_id"] == b["artifact_id"]


def test_duplicate_input_filenames_are_rejected(tmp_path):
    # Same collision the AD-13 build_meta refuses: one hash would vanish from
    # the record meant to prove provenance.
    nested = tmp_path / "nested"
    nested.mkdir()
    first = tmp_path / "bankchurners.parquet"
    second = nested / "bankchurners.parquet"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    with pytest.raises(ValueError, match="duplicate"):
        build_model_meta(b"x", inputs=[first, second], features=PREDICTOR_COLUMNS, seed=42, metrics={})


# --- save / read round trip ---------------------------------------------------


def test_save_model_with_identity_writes_both_files_and_returns_the_id(tmp_path):
    features, raw = _frames()
    inputs = _input_files(tmp_path, features, raw)
    result = fit_and_compare(features, raw)
    model_p = tmp_path / "churn_model.joblib"

    returned = save_model_with_identity(
        result.model, model_p, inputs=inputs, seed=42, metrics=result.metrics()
    )

    assert model_p.exists()
    assert artifact_id(model_p.read_bytes()) == returned
    meta = json.loads(model_meta_path(model_p).read_text(encoding="utf-8"))
    assert meta["artifact_id"] == returned
    assert read_model_meta(model_p)["artifact_id"] == returned


def test_read_model_meta_fails_fast_when_the_record_is_missing(tmp_path):
    with pytest.raises(ArtifactIdentityError):
        read_model_meta(tmp_path / "churn_model.joblib")


def test_read_model_meta_fails_fast_on_a_malformed_record(tmp_path):
    model_p = tmp_path / "churn_model.joblib"
    model_p.write_bytes(b"x")
    model_meta_path(model_p).write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactIdentityError):
        read_model_meta(model_p)


def test_a_failed_meta_write_leaves_the_previous_artifact_in_place(tmp_path, monkeypatch):
    features, raw = _frames()
    inputs = _input_files(tmp_path, features, raw)
    result = fit_and_compare(features, raw)
    model_p = tmp_path / "churn_model.joblib"
    save_model_with_identity(result.model, model_p, inputs=inputs, seed=42, metrics={})
    previous_bytes = model_p.read_bytes()

    import crm.common.atomic as atomic

    def _boom(target, text):
        raise OSError("disk full")

    monkeypatch.setattr(atomic, "atomic_write_text", _boom)
    with pytest.raises(OSError):
        save_model_with_identity(result.model, model_p, inputs=inputs, seed=42, metrics={})

    assert model_p.read_bytes() == previous_bytes
    assert model_meta_path(model_p).exists()


# --- binding the scored frame -------------------------------------------------


def test_attach_artifact_id_stamps_every_row_without_mutating_the_input():
    features, raw = _frames()
    result = fit_and_compare(features, raw)
    before = result.scored.copy()

    stamped = attach_artifact_id(result.scored, "a" * 64)

    assert list(stamped.columns) == ["CLIENTNUM", "churn_prob", "artifact_id"]
    assert stamped["artifact_id"].unique().tolist() == ["a" * 64]
    pd.testing.assert_frame_equal(result.scored, before)


@pytest.mark.parametrize("bad", ["", None, 42])
def test_attach_artifact_id_rejects_a_missing_id(bad):
    features, raw = _frames()
    scored = fit_and_compare(features, raw).scored
    with pytest.raises((ValueError, TypeError)):
        attach_artifact_id(scored, bad)


def test_verify_artifact_identity_raises_on_mismatch():
    # The AD-5 rule is FAIL, not warn. An implementation that logs and returns
    # is killed by this test.
    verify_artifact_identity("a" * 64, "a" * 64, context="scored")
    with pytest.raises(ArtifactIdentityError, match="scored"):
        verify_artifact_identity("a" * 64, "b" * 64, context="scored")


def test_identity_is_consistent_across_a_real_save_and_stamp(tmp_path):
    features, raw = _frames()
    inputs = _input_files(tmp_path, features, raw)
    result = fit_and_compare(features, raw)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"

    aid = save_model_with_identity(result.model, model_p, inputs=inputs, seed=42, metrics={})
    attach_artifact_id(result.scored, aid).to_parquet(scored_p, index=False)

    assert identity_is_consistent(model_p, scored_p) is True


@pytest.mark.parametrize("break_it", ["tamper", "drop_column", "two_ids", "no_meta", "no_scored"])
def test_identity_is_consistent_is_fail_closed(tmp_path, break_it):
    features, raw = _frames()
    inputs = _input_files(tmp_path, features, raw)
    result = fit_and_compare(features, raw)
    model_p = tmp_path / "churn_model.joblib"
    scored_p = tmp_path / "churn_scored.parquet"
    aid = save_model_with_identity(result.model, model_p, inputs=inputs, seed=42, metrics={})
    scored = attach_artifact_id(result.scored, aid)

    if break_it == "tamper":
        scored["artifact_id"] = "b" * 64
    elif break_it == "drop_column":
        scored = scored.drop(columns=["artifact_id"])
    elif break_it == "two_ids":
        scored.loc[0, "artifact_id"] = "b" * 64
    scored.to_parquet(scored_p, index=False)

    if break_it == "no_meta":
        model_meta_path(model_p).unlink()
    if break_it == "no_scored":
        scored_p.unlink()

    assert identity_is_consistent(model_p, scored_p) is False
