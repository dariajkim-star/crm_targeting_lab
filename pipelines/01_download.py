"""Stage 01: acquire BankChurners + Online Retail II as raw parquet (+ meta).

Run: .venv/Scripts/python.exe pipelines/01_download.py
(`python -m pipelines.01_download` cannot work - the module name starts with a
digit. README "Data acquisition" documents the manual fallback.)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config  # noqa: E402
from crm.common.acquisition import FALLBACK_HINT, acquire_kaggle_csv  # noqa: E402

SOURCES = (
    ("sakshigoyal7/credit-card-customers", "BankChurners.csv"),
    ("mashlyn/online-retail-ii-uci", "online_retail_II.csv"),
)


def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    if len(output_paths) != len(SOURCES):
        raise ValueError(f"01_download expects {len(SOURCES)} output paths, got {len(output_paths)}")
    config.ensure_output_dirs()
    # Sequential on purpose (AD-1): one dataset in flight at a time.
    for (slug, glob), dest in zip(SOURCES, output_paths, strict=True):
        logging.info("01_download: %s rows=%d", dest.name, acquire_kaggle_csv(slug, glob, dest))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        main([], [config.DATA_DIR / "bankchurners.parquet", config.DATA_DIR / "online_retail.parquet"])
    except Exception as err:
        logging.error("01_download FAILED: %s\n%s", err, FALLBACK_HINT)
        raise SystemExit(1) from err
