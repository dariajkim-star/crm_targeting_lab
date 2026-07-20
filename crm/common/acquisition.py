"""Dataset-agnostic acquisition helpers (story 1-1b).

Deliberately knows NOTHING about BankChurners or Online Retail II: slugs, file
globs and destinations arrive as arguments. Baking a dataset name in here would
put lane knowledge into shared utilities (AD-1).

Raw data is stored AS-IS: no column selection, no dtype coercion, no filtering.
Those are feature-stage decisions (story 1-3); doing them here would leak lane
logic into the acquisition stage.

Functions are stateless; all writes go through ``crm.common.atomic`` so a
failed download leaves nothing behind (AD-13).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from crm.common import atomic, freshness

STAGE_DOWNLOAD = "01_download"


def kaggle_csv_path(slug: str, filename_glob: str) -> Path:
    """Download a Kaggle dataset (anonymous; no account needed) and locate one CSV.

    Raises FileNotFoundError when the glob matches nothing - a changed upstream
    layout must fail loudly, not continue with a wrong file.
    """
    import kagglehub  # imported here so tests of other helpers do not need it

    dataset_dir = Path(kagglehub.dataset_download(slug))
    matches = sorted(dataset_dir.rglob(filename_glob))
    if not matches:
        raise FileNotFoundError(
            f"no file matching '{filename_glob}' in Kaggle dataset '{slug}' "
            f"(downloaded to {dataset_dir}) - upstream layout may have changed"
        )
    return matches[0]


def store_csv_as_parquet(csv_path: Path, dest_parquet: Path, stage: str = STAGE_DOWNLOAD) -> int:
    """Load a raw CSV verbatim and store it as (parquet + meta). Returns rows.

    ``low_memory=False`` reads each column in one pass so mixed-type columns
    (Online Retail II invoice ids) do not end up chunk-dependently typed -
    determinism of the RAW artifact matters because its hash goes into meta.
    """
    frame = pd.read_csv(csv_path, low_memory=False)
    rows = len(frame)
    meta = freshness.build_meta(stage=stage, inputs=[csv_path], rows=rows)
    atomic.write_with_meta(dest_parquet, lambda tmp: frame.to_parquet(tmp, index=False), meta=meta)
    return rows


def acquire_kaggle_csv(slug: str, filename_glob: str, dest_parquet: Path) -> int:
    """Full acquisition path for one dataset: download -> store -> row count."""
    return store_csv_as_parquet(kaggle_csv_path(slug, filename_glob), dest_parquet)
