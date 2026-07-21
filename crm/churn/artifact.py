"""Model persistence AND artifact identity for the churn stage (1-6a, 1-6b).

WHAT IDENTITY BUYS (AD-5). ``models/`` is gitignored, so a mismatch between the
model and the scores derived from it cannot be detected after the fact. Story
1-6a wrote the model and the scores as two separately-atomic files: a crash
between them left "new model + old scores" with nothing to notice it. Here each
scored row carries the model's CONTENT HASH, so the next stage run - and every
consumer (1-7 SHAP, the 4-1 mart) - can prove the scores describe the model that
is actually on disk. The crash window still exists; it changes from UNDETECTABLE
to DETECTED-AND-RECOMPUTED ON THE NEXT RUN, not repaired at the moment of the
crash.

``artifact_id`` IS DEFINED AS the SHA-256 of the serialized model BYTES. Later
stories must not re-derive it some other way. Consequences, stated plainly:

  - It proves SAME MODEL CONTENT, not same training RUN. Retraining on the same
    data with the same seed yields the same id, so scores from an earlier
    identical run also verify. That is the intended reading of AD-5 here -
    identical content is the same artifact - and it is why nothing in this
    module claims two files came from one execution. Distinguishing executions
    would need a separate per-run nonce, which nothing downstream asks for.
  - Reproducibility is scoped to a FIXED ENVIRONMENT. Measured 2026-07-21 on
    python 3.12.10 / joblib 1.5.3 / xgboost 3.3.0: the bytes are identical
    across processes. A different interpreter, pickle protocol, library version
    or platform may serialise the same model differently and yield a different
    id. That direction is safe (a new id causes a retrain, never a false match);
    cross-environment stability would require a canonical XGBoost payload.
  - It does NOT detect input drift. That is AD-13's job (``config_hash`` +
    recorded input hashes), already wired into the stage's freshness gate. The
    two mechanisms answer different questions - AD-13: "must this be
    recomputed?", AD-5: "do these outputs describe the same model?" - and must
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
import logging
import platform
import re
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Iterable, Sequence

import joblib
import pandas as pd

from crm.churn.model import ALL_PREDICTOR_COLUMNS
from crm.common.atomic import write_with_meta
from crm.common.freshness import file_sha256, sha256_bytes

__all__ = [
    "ArtifactIdentityError",
    "serialize_model",
    "artifact_id",
    "model_meta_path",
    "build_model_meta",
    "save_model_with_identity",
    "read_model_meta",
    "read_verified_model_meta",
    "verify_artifact_identity",
    "identity_is_consistent",
    "outputs_share_identity",
]

_LOG = logging.getLogger(__name__)
_ID_COLUMN = "artifact_id"
# An artifact_id is a SHA-256 hex digest and nothing else. Without this a record
# carrying `42` or a truncated hash would sail through every comparison below.
_ID_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")
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
    features: Sequence[str] = ALL_PREDICTOR_COLUMNS,
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


def read_model_meta(model_path: Path) -> dict[str, Any]:
    """Load the AD-5 record, failing loudly when it is missing or unusable.

    Consumers are entitled to assume a returned record is real; returning None
    or an empty dict here would push the failure downstream to whoever forgets
    to check. This reads the RECORD only - use ``read_verified_model_meta`` to
    also prove the record describes the model file that is actually on disk.
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
    if not isinstance(meta, dict):
        raise ArtifactIdentityError(f"identity record {meta_file.name} is not a JSON object")
    recorded = meta.get("artifact_id")
    if not isinstance(recorded, str) or not _ID_PATTERN.match(recorded):
        raise ArtifactIdentityError(
            f"identity record {meta_file.name} carries no usable artifact_id "
            f"(expected a 64-char sha256 hex digest, got {recorded!r})"
        )
    return meta


def read_verified_model_meta(model_path: Path) -> dict[str, Any]:
    """Load the AD-5 record AND prove it describes the model file on disk.

    The record alone proves nothing about the artifact: swap the ``.joblib`` for
    a different (perfectly valid) model and leave the record untouched, and a
    record-only check still says everything agrees - which is precisely the
    failure AD-5 exists to prevent. Hashing the file closes that.

    This is the function consumers (1-7 SHAP, the 4-1 mart) must call.
    """
    if not model_path.exists():
        raise ArtifactIdentityError(f"missing model artifact: {model_path} - rerun 03_train_churn")
    meta = read_model_meta(model_path)
    verify_artifact_identity(meta["artifact_id"], file_sha256(model_path), context=model_path.name)
    return meta


def verify_artifact_identity(expected: str, actual: str, *, context: str) -> None:
    """Fail immediately when two ids describe different model content (AD-5).

    A warning would be worse than useless here: the whole point is that a
    ``churn_prob`` and an explanation of it must not be presented together
    unless they describe the same model.
    """
    if expected != actual:
        raise ArtifactIdentityError(
            f"artifact_id mismatch for {context}: the record says '{expected}', "
            f"{context} says '{actual}' - they describe DIFFERENT model content; "
            f"rerun 03_train_churn"
        )


def outputs_share_identity(model_path: Path, *derived_paths: Path) -> bool:
    """True only if EVERY derived output carries the on-disk model's identity.

    Story 1-7 adds a third output (SHAP values) that must be bound to the same
    training run as the scores. Checking them one at a time in the stage would
    put branching logic where the shape guard forbids it, and checking only the
    first would let a stale SHAP frame survive a rerun.
    """
    if not derived_paths:
        raise ValueError("pass at least one derived output to check")
    return all(identity_is_consistent(model_path, path) for path in derived_paths)


def identity_is_consistent(model_path: Path, scored_path: Path) -> bool:
    """True only if the scored file provably came from the model file on disk.

    Three things must agree: the model BYTES, the identity record, and the id
    stamped on the scores. Checking only the last two would let a swapped or
    corrupted ``.joblib`` pass.

    Fail-closed: a missing file, an unreadable record, a scored frame with no
    ``artifact_id``, more than one id in it, or a mismatch all read as False -
    the caller reruns. Nothing here raises, because "cannot prove it" and "it is
    wrong" lead to the same action for a freshness gate. The REASON is logged
    rather than swallowed: a persistent inconsistency would otherwise show up
    only as an expensive retrain on every single run, with nothing to say why.
    """
    try:
        expected = read_verified_model_meta(model_path)[_ID_COLUMN]
    except ArtifactIdentityError as err:
        _LOG.info("identity inconsistent: %s", err)
        return False
    if not scored_path.exists():
        _LOG.info("identity inconsistent: no scored output at %s", scored_path)
        return False
    # Deliberately broad: for a freshness GATE, every way of failing to read the
    # stamp means the same thing - we cannot prove consistency, so recompute. A
    # narrow tuple leaks whatever the parquet backend happens to raise this
    # version, and that exception would surface as a crash from a function whose
    # entire contract is "returns False when unsure".
    try:
        ids = pd.read_parquet(scored_path, columns=[_ID_COLUMN])[_ID_COLUMN].unique()
    except Exception as err:  # noqa: BLE001 - see above
        _LOG.info("identity inconsistent: cannot read %s from %s (%s)",
                  _ID_COLUMN, scored_path.name, err)
        return False
    if len(ids) != 1:
        _LOG.info("identity inconsistent: %s carries %d distinct artifact_ids", scored_path.name, len(ids))
        return False
    stamped = ids[0]
    # A null or non-string stamp must not reach the comparison: with pandas'
    # nullable strings `pd.NA != expected` is pd.NA, and returning that makes the
    # caller's `if` raise "boolean value of NA is ambiguous" - a crash out of a
    # fail-closed function.
    if stamped is None or not isinstance(stamped, str) or pd.isna(stamped):
        _LOG.info("identity inconsistent: %s carries no usable artifact_id (%r)",
                  scored_path.name, stamped)
        return False
    if stamped != expected:
        _LOG.info("identity inconsistent: scores carry '%s', model is '%s'", stamped, expected)
        return False
    return True
