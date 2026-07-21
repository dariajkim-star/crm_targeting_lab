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
    # Compare by CLIENTNUM after reset_index (review High): the earlier version
    # preserved the index and compared sort_index(), so a mutation that sorted by
    # INDEX instead of CLIENTNUM slipped through. reset_index destroys any index
    # correlation, forcing the comparison onto the customer key.
    original = (
        df.assign(segment_id=assign_segments(df, k=4)).set_index("CLIENTNUM")["segment_id"].sort_index()
    )
    shuffled = df.sample(frac=1, random_state=13).reset_index(drop=True)
    after = (
        shuffled.assign(segment_id=assign_segments(shuffled, k=4))
        .set_index("CLIENTNUM")["segment_id"].sort_index()
    )
    pd.testing.assert_series_equal(original, after, check_names=False)


def test_kmeans_receives_explicit_seed_and_n_init(monkeypatch):
    # AD-7 requires the seed AND an explicit n_init injected into KMeans. A pure
    # behaviour test cannot see this - with a fixed seed the run is deterministic
    # whether or not n_init is explicit, and "different seed differs" is a fragile
    # oracle (a clear global optimum can converge identically). So spy on the
    # constructor and assert the exact kwargs (review Med / Low).
    import crm.segment.segments as mod

    captured = {}
    RealKMeans = mod.KMeans

    class SpyKMeans(RealKMeans):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(mod, "KMeans", SpyKMeans)
    df = _tiered(20, [9000, 6000, 3000, 500])
    assign_segments(df, k=4, seed=123)
    assert captured.get("random_state") == 123  # the passed seed, not seed+1
    assert captured.get("n_init") == mod._N_INIT  # explicit, never "auto"
    assert captured.get("n_clusters") == 4


def test_mean_breaks_median_ties_in_exact_order():
    # median-equal but mean-different clusters: the reorder must fall through
    # median -> MEAN, so the higher-mean cluster gets the lower segment_id. A
    # tiebreak of only [median, label] would order these arbitrarily (review Med).
    # A: recency 0, monetary [4000,5000,6000] -> median 5000, mean 5000
    # B: recency 9, monetary [1000,5000,12000] -> median 5000, mean 6000
    # C: recency 4, monetary [100,150,200]    -> clearly lowest
    rows = []
    cid = 0
    for rec, mons in [(0, [4000, 5000, 6000]), (9, [1000, 5000, 12000]), (4, [100, 150, 200])]:
        for m in mons:
            rows.append({"CLIENTNUM": cid, "recency_proxy": rec, "frequency_proxy": rec * 3,
                         "monetary_proxy": float(m), "R_score": 1, "F_score": 1, "M_score": 1})
            cid += 1
    df = _rfm_frame(rows)
    seg = assign_segments(df, k=3)
    labelled = df.assign(segment_id=seg)
    seg_b = labelled.loc[labelled["recency_proxy"] == 9, "segment_id"].iloc[0]
    seg_a = labelled.loc[labelled["recency_proxy"] == 0, "segment_id"].iloc[0]
    assert seg_b < seg_a  # higher mean (B) precedes equal-median lower-mean (A)


def test_scale_invariance_relies_on_standardisation():
    # StandardScaler makes clustering invariant to a linear rescale of a feature.
    # Multiplying monetary by 1e6 must NOT change any customer's segment_id (value
    # ORDER is preserved, so the value-ordered ids are stable too). Without the
    # scaler, monetary would dominate the distance and segments would move - this
    # kills a "scaler removed" mutation. Fuzzy fixture so the effect is real.
    rows = [
        {"CLIENTNUM": i, "recency_proxy": i % 6, "frequency_proxy": 10 + (i % 30),
         "monetary_proxy": 500.0 + (i * 37 % 9000), "R_score": 1, "F_score": 1, "M_score": 1}
        for i in range(300)
    ]
    df = _rfm_frame(rows)
    scaled = df.copy()
    scaled["monetary_proxy"] = scaled["monetary_proxy"] * 1_000_000
    base = df.assign(s=assign_segments(df, k=4)).set_index("CLIENTNUM")["s"].sort_index()
    after = scaled.assign(s=assign_segments(scaled, k=4)).set_index("CLIENTNUM")["s"].sort_index()
    pd.testing.assert_series_equal(base, after, check_names=False)


# --- customer-table contract (review High) -----------------------------------

def test_duplicate_clientnum_is_rejected():
    df = _tiered(10, [9000, 3000])
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        assign_segments(dup, k=2)


def test_null_clientnum_is_rejected():
    df = _tiered(10, [9000, 3000])
    df.loc[0, "CLIENTNUM"] = None
    with pytest.raises(ValueError, match="null"):
        assign_segments(df, k=2)


def test_duplicate_index_still_maps_each_customer_correctly():
    # A non-unique DataFrame index must not corrupt the per-customer mapping: the
    # restore is by CLIENTNUM, not by index (review High reproduction 2).
    df = _tiered(15, [9000, 5000, 1000])
    df.index = [0] * len(df)  # pathological duplicate index
    seg = assign_segments(df, k=3)
    per_customer = df.assign(s=seg.to_numpy()).groupby("CLIENTNUM")["s"].nunique()
    assert (per_customer == 1).all()


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")
def test_too_few_distinct_vectors_is_rejected():
    # KMeans would return < k clusters on all-identical rows; the 1..k contract
    # must fail loudly instead of returning a single segment (review Med).
    df = _tiered(6, [1000])  # one tier, all identical monetary; degenerate for k=4
    with pytest.raises(ValueError, match="distinct clusters"):
        assign_segments(df, k=4)


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
