"""Behavioural tests for K-means segmentation and value-ordered stable IDs.

Behaviour-based, not tautological (1-3 lesson): tests never re-run KMeans and
compare. They assert the PROPERTIES that matter - segment 1 is the highest-value
tier, IDs are invariant to row order, the seed is really injected - via synthetic
data with a known value hierarchy plus determinism checks.
"""

from __future__ import annotations

import pandas as pd
import pytest

from crm.config import SEGMENT_K
from crm.segment.features import RFM_OUTPUT_COLUMNS
from crm.segment.segments import (
    FEATURE_TABLE_COLUMNS,
    assign_segments,
    build_feature_table,
)


def _rfm_frame(rows: list[dict]) -> pd.DataFrame:
    """A story-1-3-shaped feature frame (the columns assign_segments consumes)."""
    return pd.DataFrame(rows)[list(RFM_OUTPUT_COLUMNS)]


def _tiered(n_per_tier: int, tiers: list[float]) -> pd.DataFrame:
    """Well-separated value tiers: each tier is a tight blob at a monetary level,
    highest first. Lets us pin which segment_id the top blob must receive."""
    rows = []
    cid = 0
    for t_index, monetary in enumerate(tiers):
        for _ in range(n_per_tier):
            rows.append(
                {
                    "CLIENTNUM": cid,
                    "recency_proxy": t_index,
                    "frequency_proxy": 10 + t_index * 20,
                    "monetary_proxy": float(monetary),
                    "R_score": 1,
                    "F_score": 1,
                    "M_score": 1,
                }
            )
            cid += 1
    return _rfm_frame(rows)


# --- contract ----------------------------------------------------------------

def test_returns_segment_ids_one_to_k_indexed_like_input():
    df = _tiered(20, [9000, 6000, 3000, 500])
    seg = assign_segments(df, k=4)
    assert set(seg.unique()) == {1, 2, 3, 4}
    assert list(seg.index) == list(df.index)


def test_input_frame_is_not_mutated():
    df = _tiered(20, [9000, 6000, 3000, 500])
    before = df.copy(deep=True)
    assign_segments(df, k=4)
    pd.testing.assert_frame_equal(df, before)


def test_missing_column_names_it():
    df = _tiered(10, [9000, 3000]).drop(columns=["monetary_proxy"])
    with pytest.raises(KeyError, match="monetary_proxy"):
        assign_segments(df, k=2)


def test_k_out_of_range_is_rejected():
    df = _tiered(3, [9000, 3000])
    with pytest.raises(ValueError, match="k must be >= 2"):
        assign_segments(df, k=1)
    with pytest.raises(ValueError, match="exceeds the number of rows"):
        assign_segments(_tiered(1, [9000, 3000]), k=99)


# --- AC2: value-ordered stable IDs -------------------------------------------

def test_segment_one_is_the_highest_value_tier():
    # Four well-separated tiers -> KMeans recovers them; segment_id must be
    # assigned by DESCENDING median value, so the 9000 blob is segment 1 and the
    # 500 blob is segment 4, regardless of KMeans' arbitrary internal labels.
    df = _tiered(25, [9000, 6000, 3000, 500])
    seg = assign_segments(df, k=4)
    medians = df.assign(segment_id=seg).groupby("segment_id")["monetary_proxy"].median()
    assert list(medians.sort_index()) == sorted(medians, reverse=True)
    # The highest-value customers carry segment_id 1.
    top_blob = df["monetary_proxy"] == 9000
    assert set(seg[top_blob].unique()) == {1}


def test_segment_median_value_is_monotone_descending():
    df = _tiered(30, [12000, 7000, 4000, 1000])
    seg = assign_segments(df, k=4)
    medians = (
        df.assign(segment_id=seg).groupby("segment_id")["monetary_proxy"].median().sort_index()
    )
    assert medians.is_monotonic_decreasing


# --- AC3 / NFR4: determinism -------------------------------------------------

def test_deterministic_across_runs():
    df = _tiered(40, [9000, 6000, 3000, 500])
    assert assign_segments(df, k=4).equals(assign_segments(df, k=4))


def test_invariant_to_row_order():
    # KMeans is order-sensitive (k-means++ init samples in data order); the
    # canonical-sort inside assign_segments must make segment_id identical for
    # each customer regardless of input row order.
    #
    # The fixture is deliberately FUZZY (not well-separated tiers): on cleanly
    # separated blobs KMeans converges to the same clusters either way and a
    # missing sort would slip through (the 1-3 Med-5 lesson). This data genuinely
    # yields different labels without the canonical sort.
    rows = [
        {"CLIENTNUM": i, "recency_proxy": i % 6, "frequency_proxy": 10 + (i % 30),
         "monetary_proxy": 500.0 + (i * 37 % 9000), "R_score": 1, "F_score": 1, "M_score": 1}
        for i in range(300)
    ]
    df = _rfm_frame(rows)
    original = assign_segments(df, k=4)
    shuffled = df.sample(frac=1, random_state=13)
    after = assign_segments(shuffled, k=4)
    pd.testing.assert_series_equal(
        original.sort_index(), after.sort_index(), check_names=False
    )


def test_seed_is_actually_injected():
    # A different seed generally yields a different clustering; if the seed were
    # ignored, both calls would be identical and this would fail. Uses a fuzzy,
    # not-cleanly-separated frame so the seed can actually change the outcome.
    rows = [
        {"CLIENTNUM": i, "recency_proxy": i % 6, "frequency_proxy": 10 + (i % 30),
         "monetary_proxy": 500.0 + (i * 37 % 9000), "R_score": 1, "F_score": 1, "M_score": 1}
        for i in range(300)
    ]
    df = _rfm_frame(rows)
    assert not assign_segments(df, k=4, seed=1).equals(assign_segments(df, k=4, seed=999))


def test_median_tie_break_is_deterministic():
    # Two tiers share the SAME median value -> the reorder must fall through to a
    # total-order tiebreak, and repeated runs must agree.
    df = _tiered(20, [5000, 5000, 1000])
    first = assign_segments(df, k=3)
    second = assign_segments(df, k=3)
    pd.testing.assert_series_equal(first, second)


# --- build_feature_table: full stage output ----------------------------------

def test_build_feature_table_has_rfm_plus_segment_id():
    from crm.segment.value import customer_value  # noqa: F401 (schema anchor)
    import numpy as np

    df = pd.DataFrame(
        {
            "CLIENTNUM": range(60),
            "Months_Inactive_12_mon": np.arange(60) % 6,
            "Total_Trans_Ct": 10 + np.arange(60),
            "Total_Trans_Amt": 500 + np.arange(60) * 100,
        }
    )
    out = build_feature_table(df)
    assert list(out.columns) == list(FEATURE_TABLE_COLUMNS)
    assert "segment_id" in out.columns
    assert set(out["segment_id"].unique()) == set(range(1, SEGMENT_K + 1))
    assert len(out) == 60
