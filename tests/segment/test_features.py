"""Behavioural tests for RFM proxy features (AC2, AC4, AC5).

Behaviour-based, NOT tautological (NFR6, P1 2-2 sign-flip lesson): tests assert
KNOWN input -> expected rank/bucket RELATIONSHIPS, and one hand-written oracle
pins exact bucket numbers. They never recompute the implementation's own qcut
and compare. The 1-2 review taught that property checks ALONE let clip/rescale
mutations pass, so a fixed oracle sits alongside the monotonicity properties.
"""

from __future__ import annotations

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

def test_leakage_columns_are_excluded():
    df = _spread(30)
    df["Naive_Bayes_Classifier_Attrition_Flag_a_1"] = 0.0
    df["Naive_Bayes_Classifier_Attrition_Flag_a_2"] = 1.0
    out = compute_rfm_features(df)
    assert not [c for c in out.columns if "Naive_Bayes" in c]


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

def test_hardcoded_oracle_bucket_assignment():
    # Five customers, strictly increasing amount, quintiles => each lands in its
    # own bucket 1..5 in amount order. Bucket numbers are pinned by hand, not
    # recomputed. A top-clip or a piecewise rescale would move these.
    df = _frame(
        [
            {"CLIENTNUM": c, "Months_Inactive_12_mon": 2, "Total_Trans_Ct": 40,
             "Total_Trans_Amt": amt}
            for c, amt in [(1, 500), (2, 1500), (3, 3000), (4, 6000), (5, 12000)]
        ]
    )
    out = compute_rfm_features(df, quantiles=5).set_index("CLIENTNUM")
    assert list(out.loc[[1, 2, 3, 4, 5], "M_score"]) == [1, 2, 3, 4, 5]


# --- AC4-adjacent: determinism (AD-7) ----------------------------------------

def test_deterministic_across_runs():
    df = _spread(200)
    first = compute_rfm_features(df)
    second = compute_rfm_features(df)
    pd.testing.assert_frame_equal(first, second)
