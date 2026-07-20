"""Acquisition guards (story 1-1b review).

``kaggle_csv_path`` needs the network and is exercised by the real pipeline run;
what is unit-testable - and what actually bit - is the storage path's handling
of degenerate input.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from crm.common import acquisition, freshness


def test_store_csv_as_parquet_roundtrips_and_writes_meta(tmp_path: Path) -> None:
    csv = tmp_path / "raw.csv"
    pd.DataFrame({"a": [1, 2, 3]}).to_csv(csv, index=False)
    dest = tmp_path / "out.parquet"

    rows = acquisition.store_csv_as_parquet(csv, dest)

    assert rows == 3
    assert pd.read_parquet(dest)["a"].tolist() == [1, 2, 3]
    freshness.verify_inputs([dest], expected_stage="01_download")  # must not raise


def test_store_csv_as_parquet_rejects_an_empty_csv(tmp_path: Path) -> None:
    """A truncated download must fail HERE, not three stages downstream."""
    csv = tmp_path / "raw.csv"
    csv.write_text("a,b\n", encoding="utf-8")  # header only
    dest = tmp_path / "out.parquet"

    with pytest.raises(ValueError, match="0 rows"):
        acquisition.store_csv_as_parquet(csv, dest)

    assert not dest.exists(), "no artifact may survive a rejected acquisition"
    assert not freshness.meta_path_for(dest).exists()
