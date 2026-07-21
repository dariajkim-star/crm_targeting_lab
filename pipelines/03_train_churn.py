"""Stage 03: train the cross-sectional churn-RISK classifier (+ score, + meta).

Cross-sectional (AD-6): Attrition_Flag is an after-the-fact snapshot label, not a
forecast. Verifies both producers, skips when fresh (model AND scored present),
writes scored parquet (+AD-13 meta) and the model. AD-5 identity is story 1-6b.
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402

from crm import config  # noqa: E402
from crm.churn.artifact import save_model  # noqa: E402
from crm.churn.model import fit_and_compare  # noqa: E402
from crm.common.atomic import write_parquet_with_meta  # noqa: E402
from crm.common.freshness import build_meta, is_output_stale, verify_inputs  # noqa: E402

def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    features_src, raw_src = input_paths
    model_out, scored_out = output_paths
    verify_inputs([features_src], expected_stage="02_features")
    verify_inputs([raw_src], expected_stage="01_download")
    # Fresh only if the MODEL also exists (a deleted sibling must force a rerun).
    if model_out.exists() and not is_output_stale(
            scored_out, [features_src, raw_src], expected_stage="03_train_churn"):
        return
    result = fit_and_compare(pd.read_parquet(features_src), pd.read_parquet(raw_src))
    save_model(result.model, model_out)
    meta = build_meta("03_train_churn", [features_src, raw_src], rows=len(result.scored))
    write_parquet_with_meta(scored_out, result.scored, meta)
    logging.info("03_train_churn: xgb PR-AUC=%.4f", result.xgboost_pr_auc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main([config.DATA_DIR / "features_customers.parquet", config.DATA_DIR / "bankchurners.parquet"],
         [config.MODELS_DIR / "churn_model.joblib", config.DATA_DIR / "churn_scored.parquet"])
