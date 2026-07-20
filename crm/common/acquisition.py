"""Dataset-agnostic acquisition helpers (story 1-1b).

Deliberately knows NOTHING about BankChurners or Online Retail II: slugs, file
globs and destinations arrive as arguments. Baking a dataset name in here would
put lane knowledge into shared utilities (AD-1).

Raw data is stored AS-IS: no column selection, no dtype coercion, no filtering.
Those are feature-stage decisions (story 1-3); doing them here would leak lane
logic into the acquisition stage.

Functions are stateless; all writes go through ``crm.common.atomic`` so a
failed download leaves nothing behind (AD-13). The pipeline layer decides WHAT
is acquired and WHERE it lands (slug, glob, destination all arrive as
arguments); this module owns only the mechanics - the layering convention as
amended in the story 1-1b review.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from crm.common import atomic, freshness

STAGE_DOWNLOAD = "01_download"

FALLBACK_HINT = (
    "Download the CSV manually from the Kaggle dataset page, then run "
    "crm.common.acquisition.store_csv_as_parquet(<csv>, <dest>). "
    'See README "Data acquisition" for the exact command.'
)


def kaggle_csv_path(slug: str, filename_glob: str) -> Path:
    """Download a Kaggle dataset (anonymous; no account needed) and locate one CSV.

    Both "no match" and "several matches" raise: a changed upstream layout must
    fail loudly. Silently taking ``matches[0]`` when the archive gained a second
    matching file is precisely the quiet-wrong-file mode this guards against.
    """
    import kagglehub  # imported here so tests of other helpers do not need it

    dataset_dir = Path(kagglehub.dataset_download(slug))
    matches = sorted(dataset_dir.rglob(filename_glob))
    if not matches:
        raise FileNotFoundError(
            f"no file matching '{filename_glob}' in Kaggle dataset '{slug}' "
            f"(downloaded to {dataset_dir}) - upstream layout may have changed"
        )
    if len(matches) > 1:
        raise FileNotFoundError(
            f"'{filename_glob}' is ambiguous in Kaggle dataset '{slug}': "
            f"{[m.name for m in matches]} - narrow the glob"
        )
    return matches[0]


def store_csv_as_parquet(csv_path: Path, dest_parquet: Path, stage: str = STAGE_DOWNLOAD) -> int:
    """Load a raw CSV verbatim and store it as (parquet + meta). Returns rows.

    ``low_memory=False`` reads each column in one pass so mixed-type columns
    (Online Retail II invoice ids) are not typed differently depending on where
    pandas happened to split chunks. That buys dtype stability for a given
    pandas version; it does NOT make the parquet bytes reproducible across
    pandas/pyarrow versions, and nothing here depends on that.

    An empty CSV raises: a zero-row artifact would sail through every freshness
    check and fail much later, far from the truncated download that caused it.
    """
    frame = pd.read_csv(csv_path, low_memory=False)
    rows = len(frame)
    if rows == 0:
        raise ValueError(f"{csv_path.name}: 0 rows - upstream file is empty or truncated")
    meta = freshness.build_meta(stage=stage, inputs=[csv_path], rows=rows)
    atomic.write_with_meta(dest_parquet, lambda tmp: frame.to_parquet(tmp, index=False), meta=meta)
    return rows


def acquire_kaggle_csv(slug: str, filename_glob: str, dest_parquet: Path) -> int:
    """Full acquisition path for one dataset: download -> store -> row count."""
    return store_csv_as_parquet(kaggle_csv_path(slug, filename_glob), dest_parquet)
