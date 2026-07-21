"""Model persistence AND artifact identity for the churn stage (1-6a, 1-6b).

WHAT IDENTITY BUYS (AD-5). ``models/`` is gitignored, so a mismatch between the
model and the scores derived from it cannot be detected after the fact. Story
1-6a wrote the model and the scores as two separately-atomic files: a crash
between them left "new model + old scores" with nothing to notice it. Here each
scored row carries the model's CONTENT HASH, so a later run - and every consumer
(1-7 SHAP, the 4-1 mart) - can prove the two came from the SAME training run.
The crash window still exists; it changes from UNDETECTABLE to SELF-HEALING,
because an inconsistent pair reads as stale and is recomputed.

``artifact_id`` IS DEFINED AS the SHA-256 of the serialized model BYTES. Later
stories must not re-derive it some other way. Consequences, stated plainly:

  - Retraining on the same data with the same seed yields the SAME id. That is
    intended: identical content is the same artifact. (Measured 2026-07-21:
    joblib's bytes for this model are stable across processes, so the hash is
    reproducible - see the story's Debug Log.)
  - It does NOT detect input drift. That is AD-13's job (``config_hash`` +
    recorded input hashes), already wired into the stage's freshness gate. The
    two mechanisms answer different questions - AD-13: "must this be
    recomputed?", AD-5: "did these two outputs come from one run?" - and must
    not be merged.
  - Seed, input hashes, feature list, library versions and metrics are RECORDED
    in the meta record but do NOT feed the hash: if they changed materially the
    model bytes changed too, and if the bytes are equal it is the same model.

Metrics ride along in the record so the baseline/XGBoost comparison is
machine-readable rather than living only in a stage log and a hand-copied report.

The AD-5 record is ``models/churn_model.meta.json`` - NOT the AD-13 freshness
sibling ``churn_model.joblib.meta.json``. Different files, different contracts.

Keeping joblib and hashing here - not in the pipeline stage - honours AD-9: a
stage calls ``crm.*`` only. Writes go through ``crm.common.atomic`` so a crashed
run never leaves a half-written artifact.
"""

from __future__ import annotations

import io
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Sequence

import joblib
import pandas as pd

from crm.churn.model import PREDICTOR_COLUMNS
from crm.common.atomic import write_with_meta
from crm.common.freshness import file_sha256, sha256_bytes

__all__ = [
    "ArtifactIdentityError",
    "serialize_model",
    "save_model",
    "artifact_id",
    "model_meta_path",
    "build_model_meta",
    "save_model_with_identity",
    "read_model_meta",
    "verify_artifact_identity",
    "identity_is_consistent",
]

_ID_COLUMN = "artifact_id"
# Versions worth recording: everything whose change can move the model bytes.
_RECORDED_PACKAGES = ("xgboost", "scikit-learn", "joblib", "numpy", "pandas")


class ArtifactIdentityError(RuntimeError):
    """The model and an artifact derived from it disagree (AD-5). Retrain."""


def serialize_model(model: Any) -> bytes:
    """Deterministic joblib serialization to an in-memory buffer.

    Returning bytes (rather than dumping straight to a path) is what lets the
    exact artifact content be hashed for ``artifact_id`` without re-reading the
    file it is about to be written to.
    """
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return buffer.getvalue()


def artifact_id(model_bytes: bytes) -> str:
    """THE identity of a trained model: SHA-256 of its serialized bytes."""
    return sha256_bytes(model_bytes)


def model_meta_path(model_path: Path) -> Path:
    """``models/churn_model.joblib`` -> ``models/churn_model.meta.json`` (AD-5).

    Derived from the model path rather than spelled out, so renaming the model
    cannot silently orphan its identity record.
    """
    return model_path.with_suffix(".meta.json")


def library_versions() -> dict[str, str]:
    """Installed versions of the packages that determine the model bytes.

    Read from the environment, never hardcoded - a stale literal would turn the
    provenance record into a confident lie.
    """
    versions: dict[str, str] = {"python": platform.python_version()}
    for package in _RECORDED_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:  # pragma: no cover - present in this env
            versions[package] = "unknown"
    return versions


def build_model_meta(
    model_bytes: bytes,
    *,
    inputs: Iterable[Path],
    features: Sequence[str],
    seed: int,
    metrics: dict[str, float],
) -> dict[str, Any]:
    """Assemble the AD-5 identity record for one training run.

    ``inputs`` are the files the run READ, hashed by name. Duplicate filenames
    are refused for the same reason AD-13's ``build_meta`` refuses them: two
    same-named inputs would collide in the dict and one hash would vanish from
    the very record meant to prove provenance.
    """
    input_list = list(inputs)
    names = [path.name for path in input_list]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise ValueError(
            f"duplicate input filenames would collide in the identity record: "
            f"{sorted(duplicates)} - pass distinguishable paths"
        )

    return {
        "artifact_id": artifact_id(model_bytes),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "random_seed": int(seed),
        "inputs": {path.name: file_sha256(path) for path in input_list},
        "features": list(features),
        "libraries": library_versions(),
        "metrics": {key: float(value) for key, value in metrics.items()},
    }


def save_model_with_identity(
    model: Any,
    model_path: Path,
    *,
    inputs: Iterable[Path],
    seed: int,
    metrics: dict[str, float],
    features: Sequence[str] = PREDICTOR_COLUMNS,
) -> str:
    """Write the model and its AD-5 identity record as one unit; return the id.

    The caller stamps the returned id onto the scored frame, which is what binds
    the two outputs to a single training run.
    """
    payload = serialize_model(model)
    meta = build_model_meta(payload, inputs=inputs, features=features, seed=seed, metrics=metrics)
    write_with_meta(
        model_path,
        lambda tmp: tmp.write_bytes(payload),
        meta,
        meta_path=model_meta_path(model_path),
    )
    return meta["artifact_id"]


def save_model(model: Any, path: Path) -> None:
    """Write model bytes WITHOUT an identity record.

    Retained for callers that only need the bytes. The pipeline uses
    ``save_model_with_identity`` - an artifact with no identity cannot be bound
    to the scores derived from it (AD-5).
    """
    write_with_meta(path, lambda tmp: tmp.write_bytes(serialize_model(model)), {},
                    meta_path=model_meta_path(path))


def read_model_meta(model_path: Path) -> dict[str, Any]:
    """Load the AD-5 record, failing loudly when it is missing or unusable.

    Consumers are entitled to assume a returned record is real; returning None
    or an empty dict here would push the failure downstream to whoever forgets
    to check.
    """
    meta_file = model_meta_path(model_path)
    if not meta_file.exists():
        raise ArtifactIdentityError(
            f"no AD-5 identity record for {model_path.name} (expected {meta_file.name}) - "
            f"rerun 03_train_churn"
        )
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as err:
        raise ArtifactIdentityError(f"unreadable identity record {meta_file.name}: {err}") from err
    if not isinstance(meta, dict) or not meta.get("artifact_id"):
        raise ArtifactIdentityError(f"identity record {meta_file.name} carries no artifact_id")
    return meta


def verify_artifact_identity(expected: str, actual: str, *, context: str) -> None:
    """Fail immediately when two artifacts claim different training runs (AD-5).

    A warning would be worse than useless here: the whole point is that a
    ``churn_prob`` and an explanation of it must not be presented together
    unless they came from the same model.
    """
    if expected != actual:
        raise ArtifactIdentityError(
            f"artifact_id mismatch for {context}: model has '{expected}', "
            f"{context} has '{actual}' - they came from different training runs; "
            f"rerun 03_train_churn"
        )


def identity_is_consistent(model_path: Path, scored_path: Path) -> bool:
    """True only if the scored file provably came from THIS model.

    Fail-closed: a missing file, an unreadable record, a scored frame with no
    ``artifact_id``, more than one id in it, or a mismatch all read as False -
    the caller reruns. Nothing here raises, because "cannot prove it" and "it is
    wrong" lead to the same action for a freshness gate.
    """
    try:
        expected = read_model_meta(model_path)["artifact_id"]
        if not scored_path.exists():
            return False
        ids = pd.read_parquet(scored_path, columns=[_ID_COLUMN])[_ID_COLUMN].unique()
    except (ArtifactIdentityError, OSError, ValueError, KeyError):
        return False
    return len(ids) == 1 and ids[0] == expected
