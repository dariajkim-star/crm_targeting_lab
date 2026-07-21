"""Behavioural tests for segment profiling (AC1, AC2).

Behaviour-based, not tautological: tests assert the invariants a profile must
satisfy (counts add up, shares are proper fractions, the join is correct, Unknown
survives, value comes only from monetary_proxy) rather than re-running the same
groupby and comparing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.segment.profile import (
    PROFILE_CATEGORICAL_COLUMNS,
    PROFILE_NUMERIC_COLUMNS,
    segment_category_shares,
    segment_profiles,
)


def _features(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _raw(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _synthetic(n_per_segment: int = 10):
    """Matched features + raw frames with a known value ordering per segment."""
    feat_rows, raw_rows = [], []
    cid = 0
    # segment_id 1..4 with descending monetary so the profile mirrors 1-4 order.
    for seg, monetary in [(1, 9000.0), (2, 6000.0), (3, 4000.0), (4, 1000.0)]:
        for i in range(n_per_segment):
            feat_rows.append({
                "CLIENTNUM": cid, "segment_id": seg,
                "monetary_proxy": monetary, "frequency_proxy": 80 - seg * 10,
                "recency_proxy": seg,
            })
            raw_rows.append({
                "CLIENTNUM": cid, "Customer_Age": 40 + seg, "Dependent_count": 2,
                "Months_on_book": 36, "Total_Relationship_Count": 3,
                "Credit_Limit": 5000.0, "Total_Revolving_Bal": 1000.0,
                "Avg_Utilization_Ratio": 0.2,
                "Gender": "F" if i % 2 else "M",
                "Education_Level": "Unknown" if i == 0 else "Graduate",
                "Marital_Status": "Married", "Income_Category": "Less than $40K",
                "Card_Category": "Blue",
            })
            cid += 1
    return _features(feat_rows), _raw(raw_rows)


# --- counts and shares -------------------------------------------------------

def test_counts_sum_to_total_and_shares_sum_to_one():
    feat, raw = _synthetic(10)
    prof = segment_profiles(feat, raw)
    assert prof["n"].sum() == len(feat)
    assert prof["share"].sum() == pytest.approx(1.0)
    assert list(prof.index) == [1, 2, 3, 4]


def test_profile_columns_are_the_declared_numeric_set():
    feat, raw = _synthetic(5)
    prof = segment_profiles(feat, raw)
    assert list(prof.columns) == ["n", "share", *PROFILE_NUMERIC_COLUMNS]


def test_category_shares_rows_sum_to_one():
    feat, raw = _synthetic(10)
    for column in PROFILE_CATEGORICAL_COLUMNS:
        shares = segment_category_shares(feat, raw, column)
        assert np.allclose(shares.sum(axis=1), 1.0)


# --- consistency with 1-4 value ordering -------------------------------------

def test_monetary_median_is_monotone_with_segment_id():
    # segment 1 is the highest-value tier (1-4). The profile must reflect that:
    # monetary_proxy median descends as segment_id ascends. Ties are fine.
    feat, raw = _synthetic(12)
    prof = segment_profiles(feat, raw)
    assert prof["monetary_proxy"].is_monotonic_decreasing


# --- join correctness --------------------------------------------------------

def test_join_pulls_the_right_customers_demographics():
    # A demographic value must land on the customer it belongs to, via CLIENTNUM
    # - not by row position. Give one customer a distinctive age and check it
    # surfaces in that customer's segment only.
    feat, raw = _synthetic(5)
    # Customer 0 is in segment 1; make their age unique and shuffle raw order.
    raw.loc[raw["CLIENTNUM"] == 0, "Customer_Age"] = 99
    shuffled_raw = raw.sample(frac=1, random_state=3)
    prof = segment_profiles(feat, shuffled_raw)
    # Only segment 1 contains customer 0; its age median shifts, others unchanged.
    assert prof.loc[1, "Customer_Age"] >= 41  # customer 0's 99 pulls seg-1 up
    assert prof.loc[4, "Customer_Age"] == 44


def test_unknown_category_is_preserved():
    feat, raw = _synthetic(10)
    shares = segment_category_shares(feat, raw, "Education_Level")
    assert "Unknown" in shares.columns
    assert (shares["Unknown"] > 0).any()


# --- AD-11: value column never appears ---------------------------------------

def test_profile_never_exposes_the_value_source_column():
    feat, raw = _synthetic(5)
    raw["Total_Trans_Amt"] = 12345  # even if raw carries it, profile must not use it
    prof = segment_profiles(feat, raw)
    assert "Total_Trans_Amt" not in prof.columns
    assert "monetary_proxy" in prof.columns  # value comes from here only


# --- purity + defensive contracts --------------------------------------------

def test_inputs_are_not_mutated():
    feat, raw = _synthetic(6)
    fbefore, rbefore = feat.copy(deep=True), raw.copy(deep=True)
    segment_profiles(feat, raw)
    segment_category_shares(feat, raw, "Gender")
    pd.testing.assert_frame_equal(feat, fbefore)
    pd.testing.assert_frame_equal(raw, rbefore)


def test_duplicate_clientnum_is_rejected():
    feat, raw = _synthetic(5)
    dup = pd.concat([feat, feat.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        segment_profiles(dup, raw)


def test_segmented_customer_without_raw_row_is_rejected():
    feat, raw = _synthetic(5)
    raw = raw[raw["CLIENTNUM"] != 0]  # drop one customer's raw row
    with pytest.raises(ValueError, match="no matching raw row"):
        segment_profiles(feat, raw)


def test_unprofiled_category_is_rejected():
    feat, raw = _synthetic(5)
    with pytest.raises(ValueError, match="not a profiled categorical"):
        segment_category_shares(feat, raw, "CLIENTNUM")
