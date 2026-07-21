"""Stage 02: build RFM proxy features from BankChurners (+ meta).

Run: .venv/Scripts/python.exe pipelines/02_features.py (module name starts with
a digit, so `python -m` cannot import it - same as 01_download).

Two freshness gates run before recompute (AD-13): verify_inputs rejects a wrong
producer or config drift; is_output_stale skips work when nothing changed and
forces recompute when the input CONTENT changed since last run (DQ2).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from crm import config  # noqa: E402
from crm.common.atomic import write_parquet_with_meta  # noqa: E402
from crm.common.freshness import build_meta, is_output_stale, verify_inputs  # noqa: E402
from crm.segment.features import compute_rfm_features  # noqa: E402


def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    (source,), (out,) = input_paths, output_paths
    verify_inputs([source], expected_stage="01_download")
    if not is_output_stale(out, [source], expected_stage="02_features"):
        logging.info("02_features: %s is fresh, skipping", out.name)
        return
    features = compute_rfm_features(pd.read_parquet(source))
    write_parquet_with_meta(out, features, build_meta("02_features", [source], rows=len(features)))
    logging.info("02_features: %s rows=%d", out.name, len(features))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main([config.DATA_DIR / "bankchurners.parquet"], [config.DATA_DIR / "features_customers.parquet"])
