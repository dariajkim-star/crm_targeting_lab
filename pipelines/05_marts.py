"""Stage 05: assemble the customer mart (Lane A only; AD-2).

AD-1 sequences two lanes, but the LTV lane (04) is NOT run here - epic-2 is
frozen, so no 04_ltv output exists. This stage performs the CUSTOMER lane alone
and says so. The mart is the committed contract surface: CLIENTNUM label join
(함정4 defence, AC2), artifact_id identity gate (AD-5/AC5), full-base row
preservation (AC4), deterministic CSV + sibling meta (AC6/AC7). All assembly and
serialization logic lives in crm.marts.customers; this stage is orchestration.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402
from crm import config  # noqa: E402
from crm.common.atomic import write_bytes_with_meta  # noqa: E402
from crm.common.freshness import build_meta  # noqa: E402
from crm.marts.customers import assert_scored_identity, build_customer_mart, serialize_mart  # noqa: E402

def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    bankchurners_src, features_src, scored_src, model_src = input_paths
    (mart_out,) = output_paths
    scored = pd.read_parquet(scored_src)
    assert_scored_identity(scored, model_src)  # AD-5: fail before assembling on a stale/foreign run
    bankchurners = pd.read_parquet(bankchurners_src)
    mart = build_customer_mart(bankchurners, pd.read_parquet(features_src), scored)
    if len(mart) != len(bankchurners):
        raise ValueError(f"mart has {len(mart)} rows, expected all {len(bankchurners)} BankChurners customers (AC4)")
    meta = build_meta("05_marts", [bankchurners_src, features_src, scored_src], rows=len(mart))
    write_bytes_with_meta(mart_out, serialize_mart(mart), meta)
    logging.info("05_marts: wrote %d-row customer mart to %s", len(mart), mart_out.name)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main([config.DATA_DIR / "bankchurners.parquet", config.DATA_DIR / "features_customers.parquet",
          config.DATA_DIR / "churn_scored.parquet", config.MODELS_DIR / "churn_model.joblib"],
         [config.MARTS_DIR / "mart_customers.csv"])
