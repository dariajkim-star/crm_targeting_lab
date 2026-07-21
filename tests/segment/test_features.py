"""Behavioural tests for RFM proxy features (AC2, AC4, AC5).

Behaviour-based, NOT tautological (NFR6, P1 2-2 sign-flip lesson): tests assert
KNOWN input -> expected rank/bucket RELATIONSHIPS, and one hand-written oracle
pins exact bucket numbers. They never recompute the implementation's own qcut
and compare. The 1-2 review taught that property checks ALONE let clip/rescale
mutations pass, so a fixed oracle sits alongside the monotonicity properties.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from crm.segment.features import RFM_OUTPUT_COLUMNS, compute_rfm_features


def _frame(rows: list[dict], index: list | None = None) -> pd.DataFrame:
    """Build a BankChurners-shaped frame. Index assigned after construction so
    pandas never aligns the dict values against a passed index (1-2 lesson)."""
    frame = pd.DataFrame(rows)
    if index is not None:
        frame.index = pd.Index(index)
    return frame


def _spread(n: int) -> pd.DataFrame:
    """n customers with strictly increasing recency/frequency/amount, so every
    quantile edge is well defined and monotonicity is unambiguous."""
    return _frame(
        [
            {
                "CLIENTNUM": 1000 + i,
                "Months_Inactive_12_mon": i % 7,
                "Total_Trans_Ct": 10 + i,
                "Total_Trans_Amt": 500 + i * 25,
            }
            for i in range(n)
        ]
    )


# --- shape / contract --------------------------------------------------------

def test_emits_exactly_the_declared_columns():
    out = compute_rfm_features(_spread(50))
    assert list(out.columns) == list(RFM_OUTPUT_COLUMNS)


def test_preserves_row_count_and_index():
    df = _spread(30)
    df.index = pd.Index([f"row-{i}" for i in range(30)])
    out = compute_rfm_features(df)
    assert len(out) == 30
    assert list(out.index) == list(df.index)  # no sort / reindex


def test_input_frame_is_not_mutated():
    df = _spread(40)
    before = df.copy(deep=True)
    compute_rfm_features(df)
    pd.testing.assert_frame_equal(df, before)


def test_missing_source_column_names_it():
    df = _spread(20).drop(columns=["Total_Trans_Ct"])
    with pytest.raises(KeyError, match="Total_Trans_Ct"):
        compute_rfm_features(df)


def test_monetary_proxy_is_float():
    out = compute_rfm_features(_spread(20))
    assert out["monetary_proxy"].dtype == float


# --- AC5: leakage columns never enter the feature table ----------------------

# The two target-correlated (+/-1.0000) classifier columns BankChurners ships,
# spelled in FULL (review Med-6: an abbreviated `_a_1` fake let a targeted
# re-attach of the REAL columns survive). AC5's blast radius is an AUC-1.0 leak,
# so the guard must be proven against the exact names.
_REAL_LEAK_COLUMNS = (
    "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
    "Dependent_count_Education_Level_Months_Inactive_12_mon_1",
    "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
    "Dependent_count_Education_Level_Months_Inactive_12_mon_2",
)


def test_real_leakage_columns_are_excluded():
    df = _spread(30)
    for col in _REAL_LEAK_COLUMNS:
        df[col] = 0.0
    out = compute_rfm_features(df)
    assert list(out.columns) == list(RFM_OUTPUT_COLUMNS)
    for col in _REAL_LEAK_COLUMNS:
        assert col not in out.columns


def _load_stage_02():
    """Import pipelines/02_features.py by path (module name starts with a digit
    so a normal import cannot reach it)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "pipelines" / "02_features.py"
    spec = importlib.util.spec_from_file_location("stage_02_features", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_leakage_columns_absent_from_real_stage_output(tmp_path):
    # review Med-6 (2nd round): the earlier test wired compute_rfm_features +
    # write_parquet_with_meta by hand and never ran the STAGE, so a regression
    # that writes the source frame instead of features would pass. This invokes
    # pipelines/02_features.py::main() for real, through both freshness gates.
    from crm.common.freshness import build_meta

    src = tmp_path / "bankchurners.parquet"
    target = tmp_path / "features_customers.parquet"
    df = _spread(30)
    for col in _REAL_LEAK_COLUMNS:
        df[col] = 1.0
    df.to_parquet(src, index=False)
    # A valid 01_download meta so verify_inputs accepts the input.
    src.with_suffix(src.suffix + ".meta.json").write_text(
        json.dumps(build_meta("01_download", [], rows=len(df))), encoding="utf-8"
    )

    stage = _load_stage_02()
    stage.main([src], [target])

    written = pd.read_parquet(target)
    # Story 1-4 extended the stage output with segment_id (FEATURE_TABLE_COLUMNS).
    # The leakage-exclusion guarantee (AC5) must still hold on the new contract.
    from crm.segment.segments import FEATURE_TABLE_COLUMNS

    assert list(written.columns) == list(FEATURE_TABLE_COLUMNS)
    for col in _REAL_LEAK_COLUMNS:
        assert col not in written.columns


def test_stage_output_is_deterministic_across_two_runs(tmp_path):
    # AD-7 acceptance: run the REAL stage twice into SEPARATE outputs (running
    # into the same output twice would just hit the freshness skip and prove
    # nothing) and require identical data. Catches any non-determinism the
    # function-level tests miss - e.g. a stray reorder in the stage (review Med).
    from crm.common.freshness import build_meta

    src = tmp_path / "bankchurners.parquet"
    df = _spread(60)
    df.to_parquet(src, index=False)
    src.with_suffix(src.suffix + ".meta.json").write_text(
        json.dumps(build_meta("01_download", [], rows=len(df))), encoding="utf-8"
    )

    stage = _load_stage_02()
    out_a, out_b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    stage.main([src], [out_a])
    stage.main([src], [out_b])

    a = pd.read_parquet(out_a).sort_values("CLIENTNUM").reset_index(drop=True)
    b = pd.read_parquet(out_b).sort_values("CLIENTNUM").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


# --- AC2: behavioural score properties ---------------------------------------

def test_frequency_score_is_monotone_with_frequency():
    # Higher transaction count => score never decreases. A sign flip or a
    # scramble breaks this without reimplementing the formula.
    out = compute_rfm_features(_spread(100)).sort_values("frequency_proxy")
    assert out["F_score"].is_monotonic_increasing


def test_monetary_score_is_monotone_with_value():
    out = compute_rfm_features(_spread(100)).sort_values("monetary_proxy")
    assert out["M_score"].is_monotonic_increasing


def test_frequency_and_monetary_use_distinct_sources():
    # Discriminating case: frequency and amount are ANTI-correlated. If F were
    # wired to the value axis (or M to the count), one of these monotonicities
    # would break. With `_spread` alone both rise together and the swap hides.
    df = _frame(
        [
            {"CLIENTNUM": i, "Months_Inactive_12_mon": 2,
             "Total_Trans_Ct": 10 + i, "Total_Trans_Amt": 5000 - i * 30}
            for i in range(100)
        ]
    )
    out = compute_rfm_features(df)
    by_freq = out.sort_values("frequency_proxy")
    by_amt = out.sort_values("monetary_proxy")
    assert by_freq["F_score"].is_monotonic_increasing
    assert by_amt["M_score"].is_monotonic_increasing
    # And they genuinely disagree (F high where M low), so a shared source fails.
    assert by_freq["M_score"].is_monotonic_decreasing


def test_recency_score_inverts_inactivity():
    # THE polarity test (P1 2-2): fewer inactive months = more recent = HIGHER
    # R score. Sorting by raw recency ascending must make R_score NON-increasing.
    df = _frame(
        [
            {"CLIENTNUM": i, "Months_Inactive_12_mon": m, "Total_Trans_Ct": 20 + i,
             "Total_Trans_Amt": 600 + i * 10}
            for i, m in enumerate([0, 1, 2, 3, 4, 5, 6] * 8)
        ]
    )
    out = compute_rfm_features(df).sort_values("recency_proxy")
    assert out["R_score"].is_monotonic_decreasing


def test_scores_start_at_one():
    out = compute_rfm_features(_spread(100))
    assert out[["R_score", "F_score", "M_score"]].min().min() == 1


# --- AC2: hand-written oracle (properties alone are not enough, 1-2 review H3) -

def test_hardcoded_oracle_per_axis_bucket_assignment():
    # Exact oracle on EVERY axis (review Med-4: an M-only oracle let F/R clip
    # mutations survive). Five customers, each axis strictly increasing so a
    # 5-quantile cut puts them one-per-bucket. Bucket numbers are pinned by hand,
    # not recomputed. R inverts (fewest inactive months -> highest score).
    df = _frame(
        [
            {"CLIENTNUM": c, "Months_Inactive_12_mon": mi, "Total_Trans_Ct": tc,
             "Total_Trans_Amt": amt}
            for c, mi, tc, amt in [
                (1, 0, 10, 500),
                (2, 1, 20, 1500),
                (3, 2, 30, 3000),
                (4, 3, 40, 6000),
                (5, 4, 50, 12000),
            ]
        ]
    )
    out = compute_rfm_features(df, quantiles=5).set_index("CLIENTNUM")
    assert list(out.loc[[1, 2, 3, 4, 5], "M_score"]) == [1, 2, 3, 4, 5]
    assert list(out.loc[[1, 2, 3, 4, 5], "F_score"]) == [1, 2, 3, 4, 5]
    # R inverted: customer 1 (0 months) is most recent -> 5; customer 5 -> 1.
    assert list(out.loc[[1, 2, 3, 4, 5], "R_score"]) == [5, 4, 3, 2, 1]


def test_hardcoded_oracle_with_more_customers_than_buckets():
    # review Med-4 (2nd round): a 5-customer/5-quantile oracle cannot see a
    # mutation that INFLATES the bucket count when n > quantiles (e.g.
    # quantiles + int(nunique > quantiles)). Ten distinct values over 5 quantiles
    # must land exactly two-per-bucket 1..5. Pinned by hand.
    df = _frame(
        [
            {"CLIENTNUM": i, "Months_Inactive_12_mon": i,
             "Total_Trans_Ct": 10 + i * 5, "Total_Trans_Amt": 500 + i * 200}
            for i in range(10)
        ]
    )
    out = compute_rfm_features(df, quantiles=5).set_index("CLIENTNUM")
    assert out["F_score"].tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert out["M_score"].tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    # R inverts: fewest inactive months (customer 0) -> highest score.
    assert out["R_score"].tolist() == [5, 5, 4, 4, 3, 3, 2, 2, 1, 1]
    assert out[["R_score", "F_score", "M_score"]].max().tolist() == [5, 5, 5]


def test_empty_frame_returns_empty_feature_table():
    # review Med-3 (2nd round): the "empty" edge was claimed tested but wasn't.
    # Exercises compute_rfm_features end-to-end (incl. customer_value on empty).
    df = _spread(1).iloc[0:0]
    out = compute_rfm_features(df)
    assert out.empty
    assert list(out.columns) == list(RFM_OUTPUT_COLUMNS)


def test_quantiles_below_two_are_rejected():
    # review Med-3 (2nd round): quantiles>=2 was enforced in code but not pinned.
    with pytest.raises(ValueError, match="quantiles must be >= 2"):
        compute_rfm_features(_spread(10), quantiles=1)


def test_qcut_code_gaps_do_not_leave_score_holes():
    # review Med-3: [0,0,1,1,2,2] over 5 quantiles drops an interior code; a
    # naive code+1 would yield {1,3} with a hole at 2. Dense-ranking must give a
    # gapless {1,2}. Assert on F so a regression in the score mapping is caught.
    df = _frame(
        [
            {"CLIENTNUM": c, "Months_Inactive_12_mon": 2, "Total_Trans_Ct": ct,
             "Total_Trans_Amt": 1000}
            for c, ct in [(1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 2)]
        ]
    )
    out = compute_rfm_features(df, quantiles=5)
    assert sorted(out["F_score"].unique()) == [1, 2]  # no hole at 2


def test_single_distinct_value_scores_one():
    # review Med-3: all-equal F -> one bucket -> everyone scores 1 (not 0).
    df = _frame(
        [
            {"CLIENTNUM": c, "Months_Inactive_12_mon": 2, "Total_Trans_Ct": 40,
             "Total_Trans_Amt": 500 + c}
            for c in range(20)
        ]
    )
    out = compute_rfm_features(df)
    assert set(out["F_score"].unique()) == {1}


def test_missing_proxy_source_is_rejected():
    # review Med-3: a NaN belongs to no quantile bucket; scoring it silently
    # would put it at 0 or (inverted) above the max. Reject instead.
    df = _spread(20)
    df.loc[0, "Total_Trans_Ct"] = None
    with pytest.raises(ValueError, match="missing values"):
        compute_rfm_features(df)


# --- AC4-adjacent: determinism (AD-7) ----------------------------------------

def test_deterministic_across_runs():
    df = _spread(200)
    first = compute_rfm_features(df)
    second = compute_rfm_features(df)
    pd.testing.assert_frame_equal(first, second)


def test_scores_are_invariant_to_row_order():
    # AD-7 as WRITTEN: "same customer, same score regardless of row order"
    # (review Med-5: re-running the SAME order only proves repeatability). Uses a
    # tie-heavy fixture so a tie-break that depends on position (e.g.
    # rank(method="first")) would diverge under a shuffle.
    df = _frame(
        [
            {"CLIENTNUM": i, "Months_Inactive_12_mon": i % 3,
             "Total_Trans_Ct": 20 + (i % 5), "Total_Trans_Amt": 500 + (i % 7) * 100}
            for i in range(120)
        ]
    )
    original = compute_rfm_features(df).set_index("CLIENTNUM").sort_index()
    shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
    after = compute_rfm_features(shuffled).set_index("CLIENTNUM").sort_index()
    pd.testing.assert_frame_equal(original, after)
