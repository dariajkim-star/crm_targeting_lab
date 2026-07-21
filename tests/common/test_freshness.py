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


def test_code_commit_returns_none_when_git_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """git missing must degrade to None, never raise - meta is best-effort context.

    Simulated by making subprocess.run raise OSError (what happens when the git
    executable is absent). An earlier version of this test used chdir, which was
    inert because code_commit() pins cwd to its own directory.
    """
    def no_git(*args: object, **kwargs: object) -> None:
        raise OSError("git not found")

    monkeypatch.setattr(freshness.subprocess, "run", no_git)

    assert freshness.code_commit() is None


def test_code_commit_returns_none_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a repository git exits non-zero; that is None, not a crash."""
    class Failed:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(freshness.subprocess, "run", lambda *a, **k: Failed())

    assert freshness.code_commit() is None


def test_code_commit_returns_the_sha_when_git_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    class Succeeded:
        returncode = 0
        stdout = "deadbeef1234\n"

    monkeypatch.setattr(freshness.subprocess, "run", lambda *a, **k: Succeeded())

    assert freshness.code_commit() == "deadbeef1234"


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


def test_verify_inputs_fails_when_meta_is_json_but_not_an_object(tmp_path: Path) -> None:
    """Valid JSON that is a list/string must be a StaleInputError, not AttributeError."""
    out = tmp_path / "bankchurners.parquet"
    out.write_text("payload", encoding="utf-8")
    out.with_suffix(out.suffix + ".meta.json").write_text('["not", "an", "object"]', encoding="utf-8")

    with pytest.raises(freshness.StaleInputError, match="malformed"):
        freshness.verify_inputs([out], expected_stage="01_download")


def test_build_meta_rejects_colliding_input_filenames(tmp_path: Path) -> None:
    """Same filename from two directories would silently drop one hash."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, second = tmp_path / "a" / "raw.csv", tmp_path / "b" / "raw.csv"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    with pytest.raises(ValueError, match="duplicate input filenames"):
        freshness.build_meta(stage="02_features", inputs=[first, second], rows=1)


def test_file_sha256_rejects_a_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a file"):
        freshness.file_sha256(tmp_path)


def test_verify_inputs_reports_the_offending_path(tmp_path: Path) -> None:
    """A failure must name the file, or debugging a 5-stage pipeline is guesswork."""
    good, bad = tmp_path / "good.parquet", tmp_path / "bad.parquet"
    _write_output_with_meta(good, _valid_meta())
    _write_output_with_meta(bad, _valid_meta(config_hash="0" * 64))

    with pytest.raises(freshness.StaleInputError, match="bad.parquet"):
        freshness.verify_inputs([good, bad], expected_stage="01_download")


# --- is_output_stale: DQ2 closure (story 1-3) --------------------------------
# The consuming stage compares its OWN previous output meta's recorded input
# hashes against the inputs as they stand now. These build the output meta with
# the REAL build_meta so the recorded hashes are genuine, then observe drift.


def _output_built_from(output: Path, inputs: list[Path]) -> None:
    """Write an output + a real meta recording the current hashes of `inputs`."""
    output.write_bytes(b"features")
    meta = freshness.build_meta(stage="02_features", inputs=inputs, rows=len(inputs))
    freshness.meta_path_for(output).write_text(json.dumps(meta), encoding="utf-8")


def test_is_output_stale_false_when_inputs_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw-v1")
    out = tmp_path / "features_customers.parquet"
    _output_built_from(out, [src])
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is False


def test_is_output_stale_true_when_input_content_changed(tmp_path: Path) -> None:
    # THE DQ2 scenario: same producer, same config, but the input bytes changed
    # since our last run. verify_inputs would pass; is_output_stale must not.
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw-v1")
    out = tmp_path / "features_customers.parquet"
    _output_built_from(out, [src])
    src.write_bytes(b"raw-v2-EDITED")
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


def test_is_output_stale_true_when_output_missing(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    assert freshness.is_output_stale(tmp_path / "never_built.parquet", [src], expected_stage="02_features") is True


def test_is_output_stale_true_when_meta_missing(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    out = tmp_path / "features_customers.parquet"
    out.write_bytes(b"features")  # output exists but no meta beside it
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


def test_is_output_stale_true_when_input_set_changes(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    extra = tmp_path / "extra.parquet"
    extra.write_bytes(b"more")
    out = tmp_path / "features_customers.parquet"
    _output_built_from(out, [src])
    # An input the previous run never recorded => built from a different set.
    assert freshness.is_output_stale(out, [src, extra], expected_stage="02_features") is True


def test_is_output_stale_true_when_recorded_input_now_missing(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    out = tmp_path / "features_customers.parquet"
    _output_built_from(out, [src])
    src.unlink()
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


def test_is_output_stale_true_on_unusable_meta(tmp_path: Path) -> None:
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    out = tmp_path / "features_customers.parquet"
    out.write_bytes(b"features")
    freshness.meta_path_for(out).write_text("{not json", encoding="utf-8")
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


# --- is_output_stale: full cache key (review High-1, Low-7, Low-8) -----------


def test_is_output_stale_true_when_config_hash_drifts(tmp_path: Path) -> None:
    # THE High-1 false-fresh: output built under a different config.py, inputs
    # byte-identical. A RFM_QUANTILES change must invalidate the output even
    # though the parquet bytes never moved.
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw-stable")
    out = tmp_path / "features_customers.parquet"
    out.write_bytes(b"features-5quantile")
    meta = freshness.build_meta(stage="02_features", inputs=[src], rows=10)
    meta["config_hash"] = "0" * 64  # produced under a now-superseded config
    freshness.meta_path_for(out).write_text(json.dumps(meta), encoding="utf-8")
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


def test_is_output_stale_true_when_output_stage_mismatches(tmp_path: Path) -> None:
    # A file left at our output path by a DIFFERENT stage is not ours -> stale.
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    out = tmp_path / "features_customers.parquet"
    out.write_bytes(b"features")
    meta = freshness.build_meta(stage="99_other", inputs=[src], rows=10)
    freshness.meta_path_for(out).write_text(json.dumps(meta), encoding="utf-8")
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is True


def test_is_output_stale_rejects_empty_inputs(tmp_path: Path) -> None:
    # A consuming stage always has >=1 input; empty must raise, not read fresh
    # (guards against reuse on a network-source stage, review Low-8).
    out = tmp_path / "features_customers.parquet"
    out.write_bytes(b"features")
    with pytest.raises(ValueError, match="at least one input"):
        freshness.is_output_stale(out, [], expected_stage="02_features")


def test_is_output_stale_fresh_only_on_full_match(tmp_path: Path) -> None:
    # The positive path still returns False when stage, config and inputs all
    # agree - the new gates did not make everything stale.
    src = tmp_path / "bankchurners.parquet"
    src.write_bytes(b"raw")
    out = tmp_path / "features_customers.parquet"
    _output_built_from(out, [src])
    assert freshness.is_output_stale(out, [src], expected_stage="02_features") is False
