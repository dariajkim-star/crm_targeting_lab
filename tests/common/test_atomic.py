"""AD-13 atomic write: a failed stage leaves NOTHING behind.

Two failure shapes are covered:
  1. the writer raises mid-write  -> no output, no temp files
  2. the output lands but meta fails -> output is rolled back

Shape 2 matters because an output without its `.meta.json` is an orphan that
fails every downstream `verify_inputs` - the pipeline would be wedged in a way
whose cause is far from its symptom.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from crm.common import atomic, freshness


def _leftovers(directory: Path) -> list[str]:
    """Temp residue the writer failed to clean up.

    Matches only the module's own pattern (``.<name>.<hex>.tmp``); a broader
    "starts with a dot" rule would fail on unrelated dotfiles.
    """
    return [p.name for p in directory.iterdir() if p.name.startswith(".") and p.name.endswith(".tmp")]


# --- primitives --------------------------------------------------------------


def test_atomic_write_text_creates_the_file(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"

    atomic.atomic_write_text(target, "hello")

    assert target.read_text(encoding="utf-8") == "hello"
    assert _leftovers(tmp_path) == []


def test_atomic_write_parquet_roundtrips(tmp_path: Path) -> None:
    target = tmp_path / "out.parquet"
    frame = pd.DataFrame({"a": [1, 2, 3]})

    atomic.atomic_write_parquet(target, frame)

    assert pd.read_parquet(target)["a"].tolist() == [1, 2, 3]
    assert _leftovers(tmp_path) == []


def test_atomic_write_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    atomic.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


# --- failure shape 1: the writer raises --------------------------------------


def test_failed_write_creates_no_output_file(tmp_path: Path) -> None:
    target = tmp_path / "out.parquet"

    def exploding_writer(tmp: Path) -> None:
        tmp.write_bytes(b"partial")
        raise RuntimeError("download died halfway")

    with pytest.raises(RuntimeError):
        atomic.write_with_meta(target, exploding_writer, meta={"stage": "01_download"})

    assert not target.exists()
    assert not target.with_suffix(target.suffix + ".meta.json").exists()
    assert _leftovers(tmp_path) == []


def test_failed_write_leaves_a_previous_output_untouched(tmp_path: Path) -> None:
    """A failed rerun must not destroy the last good artifact."""
    target = tmp_path / "out.txt"
    target.write_text("previous good run", encoding="utf-8")

    def exploding_writer(tmp: Path) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        atomic.write_with_meta(target, exploding_writer, meta={"stage": "01_download"})

    assert target.read_text(encoding="utf-8") == "previous good run"


def test_failed_rerun_preserves_the_previous_meta_too(tmp_path: Path) -> None:
    """Restoring the old output while deleting its meta would CREATE an orphan.

    The pair (previous output, previous meta) must survive a failed rerun
    together - half a rollback is the very defect this module exists to stop.
    """
    target = tmp_path / "out.txt"
    target.write_text("previous good run", encoding="utf-8")
    old_meta = target.with_suffix(target.suffix + ".meta.json")
    old_meta.write_text(json.dumps({"stage": "01_download", "rows": 1}), encoding="utf-8")

    def exploding_writer(tmp: Path) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        atomic.write_with_meta(target, exploding_writer, meta={"stage": "01_download"})

    assert target.read_text(encoding="utf-8") == "previous good run"
    assert json.loads(old_meta.read_text(encoding="utf-8"))["rows"] == 1, (
        "previous meta must survive alongside the restored previous output"
    )


# --- failure shape 2: output lands, meta fails -------------------------------


def test_meta_failure_rolls_back_the_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No orphan outputs: an artifact without meta breaks every later stage."""
    target = tmp_path / "out.txt"
    original = atomic.atomic_write_text

    def fail_on_meta(path: Path, text: str) -> None:
        if path.name.endswith(".meta.json"):
            raise OSError("disk full while writing meta")
        original(path, text)

    monkeypatch.setattr(atomic, "atomic_write_text", fail_on_meta)

    with pytest.raises(OSError):
        atomic.write_with_meta(
            target, lambda tmp: tmp.write_text("payload", encoding="utf-8"), meta={"stage": "01_download"}
        )

    assert not target.exists(), "output must be rolled back when meta cannot be written"
    assert _leftovers(tmp_path) == []


def test_meta_failure_restores_the_previous_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.txt"
    target.write_text("previous good run", encoding="utf-8")
    original = atomic.atomic_write_text

    def fail_on_meta(path: Path, text: str) -> None:
        if path.name.endswith(".meta.json"):
            raise OSError("disk full while writing meta")
        original(path, text)

    monkeypatch.setattr(atomic, "atomic_write_text", fail_on_meta)

    with pytest.raises(OSError):
        atomic.write_with_meta(
            target, lambda tmp: tmp.write_text("new payload", encoding="utf-8"), meta={"stage": "01_download"}
        )

    assert target.read_text(encoding="utf-8") == "previous good run"


# --- success path ------------------------------------------------------------


def test_successful_write_produces_output_and_meta_together(tmp_path: Path) -> None:
    target = tmp_path / "bankchurners.parquet"
    frame = pd.DataFrame({"a": [1, 2]})
    meta = freshness.build_meta(stage="01_download", inputs=[], rows=len(frame))

    atomic.write_with_meta(target, lambda tmp: frame.to_parquet(tmp, index=False), meta=meta)

    assert target.exists()
    written = json.loads(target.with_suffix(target.suffix + ".meta.json").read_text(encoding="utf-8"))
    assert written["stage"] == "01_download"
    assert written["rows"] == 2
    assert _leftovers(tmp_path) == []


def test_output_written_this_way_passes_verify_inputs(tmp_path: Path) -> None:
    """End-to-end: the write path and the freshness check agree on the contract."""
    target = tmp_path / "bankchurners.parquet"
    frame = pd.DataFrame({"a": [1]})
    meta = freshness.build_meta(stage="01_download", inputs=[], rows=len(frame))

    atomic.write_with_meta(target, lambda tmp: frame.to_parquet(tmp, index=False), meta=meta)

    freshness.verify_inputs([target], expected_stage="01_download")  # must not raise
