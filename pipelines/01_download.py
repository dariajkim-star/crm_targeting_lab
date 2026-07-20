"""Stage 01: acquire BankChurners + Online Retail II as raw parquet (+ meta).

Run:  .venv/Scripts/python.exe pipelines/01_download.py
(`python -m pipelines.01_download` cannot work: the module name starts with a
digit. See README "Data acquisition" for the manual fallback.)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm import config  # noqa: E402
from crm.common.acquisition import acquire_kaggle_csv  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")

BANKCHURNERS = ("sakshigoyal7/credit-card-customers", "BankChurners.csv")
ONLINE_RETAIL = ("mashlyn/online-retail-ii-uci", "online_retail_II.csv")


def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    config.ensure_output_dirs()
    bank_dest, retail_dest = output_paths
    # Sequential on purpose (AD-1): one dataset in flight at a time.
    rows = acquire_kaggle_csv(*BANKCHURNERS, dest_parquet=bank_dest)
    logging.info("01_download: %s rows=%d", bank_dest.name, rows)
    rows = acquire_kaggle_csv(*ONLINE_RETAIL, dest_parquet=retail_dest)
    logging.info("01_download: %s rows=%d", retail_dest.name, rows)


if __name__ == "__main__":
    main([], [config.DATA_DIR / "bankchurners.parquet", config.DATA_DIR / "online_retail.parquet"])
