"""Model artifact persistence for the churn stage (story 1-6a).

``save_model`` serialises a fitted model and writes it atomically, so a crashed
or interrupted run never leaves a half-written ``.joblib`` that a later stage
would load as if it were complete (same fail-fast intent as AD-13's atomic
outputs). Keeping joblib here - not in the pipeline stage - honours AD-9: the
stage calls ``crm.*`` only, never a serialization library directly.

SCOPE: this writes the model BYTES only. The AD-5 IDENTITY record
(``churn_model.meta.json`` with ``artifact_id`` content hash, ``trained_at``,
seed, input hashes, feature list, library versions) belongs to story 1-6b, which
binds ``churn_prob`` and SHAP to one artifact. 1-6a deliberately does not write a
half version of it.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import joblib

from crm.common.atomic import atomic_write_bytes

__all__ = ["serialize_model", "save_model"]


def serialize_model(model: Any) -> bytes:
    """Deterministic-enough joblib serialization to an in-memory buffer.

    Returning bytes (rather than dumping straight to a path) lets 1-6b hash the
    exact artifact content for ``artifact_id`` without re-reading the file.
    """
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return buffer.getvalue()


def save_model(model: Any, path: Path) -> None:
    """Serialize ``model`` and write it atomically to ``path`` (temp -> rename)."""
    atomic_write_bytes(path, serialize_model(model))
