"""AD-13 freshness contract: stale partial reruns must FAIL, not warn.

The defect this guards against: developer A edits `02_features` and reruns
02 + 05; developer B reruns only 05. The mart then mixes new features with old
probabilities, nothing errors, and the committed CSV is quietly wrong.

Every test here proves a failure actually happens. A guard that logs a warning
and continues is the same as no guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crm.common import freshness


def _write_output_with_meta(path: Path, meta: dict) -> None:
    path.write_text("payload", encoding="utf-8")
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _valid_meta(**overrides: object) -> dict:
    meta = {
        "stage": "01_download",
        "created_at": "2026-07-20T00:00:00+00:00",
        "config_hash": freshness.config_hash(),
        "code_commit": "abc1234",
        "rows": 10,
        "inputs": {},
    }
    meta.update(overrides)
    return meta


# --- hashing primitives ------------------------------------------------------


def test_file_sha256_is_content_addressed(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    c.write_bytes(b"different")

    assert freshness.file_sha256(a) == freshness.file_sha256(b)
    assert freshness.file_sha256(a) != freshness.file_sha256(c)


def test_config_hash_tracks_the_config_file_bytes() -> None:
    """Defined as the SHA-256 of crm/config.py bytes - comments included.

    A comment-only edit changing the hash is INTENDED: over-invalidating is
    safer than missing a real config change.
    """
    import crm.config

    source = Path(crm.config.__file__).read_bytes()

    assert freshness.config_hash() == freshness.sha256_bytes(source)


def test_code_commit_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a git repo it returns None; freshness never depends on git."""
    monkeypatch.chdir(tmp_path)

    result = freshness.code_commit()

    assert result is None or isinstance(result, str)


# --- meta construction -------------------------------------------------------


def test_build_meta_records_input_hashes_and_rows(tmp_path: Path) -> None:
    src = tmp_path / "in.parquet"
    src.write_bytes(b"raw")

    meta = freshness.build_meta(stage="02_features", inputs=[src], rows=42)

    assert meta["stage"] == "02_features"
    assert meta["rows"] == 42
    assert meta["config_hash"] == freshness.config_hash()
    assert meta["inputs"] == {"in.parquet": freshness.file_sha256(src)}
    assert meta["created_at"]


# --- verify_inputs: the four ways a rerun goes stale -------------------------


def test_verify_inputs_accepts_fresh_predecessor_output(tmp_path: Path) -> None:
    out = tmp_path / "bankchurners.parquet"
    _write_output_with_meta(out, _valid_meta())

    freshness.verify_inputs([out], expected_stage="01_download")  # must not raise


def test_verify_inputs_fails_when_meta_is_missing(tmp_path: Path) -> None:
    out = tmp_path / "orphan.parquet"
    out.write_text("payload", encoding="utf-8")

    with pytest.raises(freshness.StaleInputError, match="meta"):
        freshness.verify_inputs([out], expected_stage="01_download")


def test_verify_inputs_fails_on_config_hash_drift(tmp_path: Path) -> None:
    """The core AD-13 scenario: input produced under a different config."""
    out = tmp_path / "bankchurners.parquet"
    _write_output_with_meta(out, _valid_meta(config_hash="0" * 64))

    with pytest.raises(freshness.StaleInputError, match="config"):
        freshness.verify_inputs([out], expected_stage="01_download")


def test_verify_inputs_fails_when_produced_by_a_different_stage(tmp_path: Path) -> None:
    out = tmp_path / "features.parquet"
    _write_output_with_meta(out, _valid_meta(stage="99_something_else"))

    with pytest.raises(freshness.StaleInputError, match="stage"):
        freshness.verify_inputs([out], expected_stage="01_download")


def test_verify_inputs_fails_when_the_input_file_is_absent(tmp_path: Path) -> None:
    with pytest.raises(freshness.StaleInputError):
        freshness.verify_inputs([tmp_path / "never_created.parquet"], expected_stage="01_download")


def test_verify_inputs_fails_on_unreadable_meta_json(tmp_path: Path) -> None:
    out = tmp_path / "bankchurners.parquet"
    out.write_text("payload", encoding="utf-8")
    out.with_suffix(out.suffix + ".meta.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(freshness.StaleInputError):
        freshness.verify_inputs([out], expected_stage="01_download")


def test_verify_inputs_reports_the_offending_path(tmp_path: Path) -> None:
    """A failure must name the file, or debugging a 5-stage pipeline is guesswork."""
    good, bad = tmp_path / "good.parquet", tmp_path / "bad.parquet"
    _write_output_with_meta(good, _valid_meta())
    _write_output_with_meta(bad, _valid_meta(config_hash="0" * 64))

    with pytest.raises(freshness.StaleInputError, match="bad.parquet"):
        freshness.verify_inputs([good, bad], expected_stage="01_download")
