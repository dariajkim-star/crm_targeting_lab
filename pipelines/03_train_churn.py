"""Stage 03: churn-RISK classifier, OUT-OF-FOLD scores + Platt calibration, SHAP,
AD-5 identity (AD-6: snapshot label, not a forecast). The artifact is a
{model, calibrator} bundle so identity covers both fitted objects. SHAP is
computed HERE only; skips when bundle, record and BOTH derived outputs agree."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402
from crm import config  # noqa: E402
from crm.churn.artifact import outputs_share_identity, save_model_with_identity  # noqa: E402
from crm.churn.explain import build_shap_output  # noqa: E402
from crm.churn.model import attach_artifact_id, fit_and_compare  # noqa: E402
from crm.common.atomic import write_parquet_with_meta  # noqa: E402
from crm.common.freshness import build_meta, is_output_stale, verify_inputs  # noqa: E402

def main(input_paths: list[Path], output_paths: list[Path]) -> None:
    features_src, raw_src = input_paths
    model_out, scored_out, shap_out = output_paths
    verify_inputs([features_src], expected_stage="02_features")
    verify_inputs([raw_src], expected_stage="01_download")
    if (model_out.exists() and outputs_share_identity(model_out, scored_out, shap_out)
            and not is_output_stale(scored_out, [features_src, raw_src],
                                    expected_stage="03_train_churn")):
        return
    seed = config.RANDOM_SEED  # ONE value: training and the record cannot disagree (AD-7)
    result = fit_and_compare(pd.read_parquet(features_src), pd.read_parquet(raw_src), seed=seed)
    aid = save_model_with_identity(result.bundle(), model_out, inputs=[features_src, raw_src],
                                   seed=seed, metrics=result.metrics())
    meta = build_meta("03_train_churn", [features_src, raw_src], rows=len(result.scored))
    write_parquet_with_meta(scored_out, attach_artifact_id(result.scored, aid), meta)
    write_parquet_with_meta(shap_out, build_shap_output(result.model, result.x, aid, seed), meta)
    logging.info("03_train_churn: xgb PR-AUC=%.4f id=%s", result.xgboost_pr_auc, aid[:12])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main([config.DATA_DIR / "features_customers.parquet", config.DATA_DIR / "bankchurners.parquet"],
         [config.MODELS_DIR / "churn_model.joblib", config.DATA_DIR / "churn_scored.parquet",
          config.DATA_DIR / "churn_shap.parquet"])
