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
    segment_attrition_rates,
    segment_category_shares,
    segment_profiles,
)


def _features(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _raw(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# Per-segment categorical make-up, DELIBERATELY DISTINCT between segments
# (review Med: an all-segments-identical fixture let a mutation that broadcast
# the GLOBAL distribution to every segment pass). Gender: seg1 all F, seg2 all
# M, seg3 3:1 F:M. Education Unknown: seg1 50%, seg2 0%.
_SEGMENT_GENDER = {1: ("F", "F", "F", "F"), 2: ("M", "M", "M", "M"),
                   3: ("F", "F", "F", "M"), 4: ("M", "M", "F", "F")}
_SEGMENT_EDU = {1: ("Unknown", "Unknown", "Graduate", "Graduate"),
                2: ("Graduate",) * 4,
                3: ("Graduate", "High School", "High School", "Unknown"),
                4: ("High School",) * 4}


def _synthetic(n_per_segment: int = 4):
    """Matched features + raw frames: descending value AND per-segment-distinct
    categorical distributions (see _SEGMENT_GENDER / _SEGMENT_EDU)."""
    feat_rows, raw_rows = [], []
    cid = 0
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
                "Gender": _SEGMENT_GENDER[seg][i % 4],
                "Education_Level": _SEGMENT_EDU[seg][i % 4],
                "Marital_Status": "Married", "Income_Category": "Less than $40K",
                "Card_Category": "Blue",
                "Attrition_Flag": "Attrited Customer" if (seg == 4 and i % 2 == 0)
                                  else "Existing Customer",
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
    # - not by row position. Three customers per segment with ages designed so
    # the MEDIAN actually moves when customer 0's age changes (review Med: the
    # earlier fixture's median was insensitive to the mutated customer).
    feat, raw = _synthetic(3)
    seg1_ids = feat.loc[feat["segment_id"] == 1, "CLIENTNUM"].tolist()
    raw.loc[raw["CLIENTNUM"] == seg1_ids[0], "Customer_Age"] = 10
    raw.loc[raw["CLIENTNUM"] == seg1_ids[1], "Customer_Age"] = 99
    raw.loc[raw["CLIENTNUM"] == seg1_ids[2], "Customer_Age"] = 100
    shuffled_raw = raw.sample(frac=1, random_state=3)
    prof = segment_profiles(feat, shuffled_raw)
    assert prof.loc[1, "Customer_Age"] == 99  # exact median oracle
    assert prof.loc[4, "Customer_Age"] == 44  # untouched segment unchanged


def test_category_shares_exact_per_segment_oracle():
    # Exact within-segment shares (review Med: identical-across-segment fixtures
    # let a "broadcast the global distribution" mutation survive). The fixture
    # gives each segment a DIFFERENT make-up, pinned here by hand.
    feat, raw = _synthetic(4)
    gender = segment_category_shares(feat, raw, "Gender")
    assert gender.loc[1, "F"] == pytest.approx(1.0)
    assert gender.loc[2, "M"] == pytest.approx(1.0)
    assert gender.loc[3, "F"] == pytest.approx(0.75)
    edu = segment_category_shares(feat, raw, "Education_Level")
    assert edu.loc[1, "Unknown"] == pytest.approx(0.5)
    assert "Unknown" not in edu.columns or edu.loc[2].get("Unknown", 0) == pytest.approx(0.0)
    assert edu.loc[4, "High School"] == pytest.approx(1.0)


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


def test_null_clientnum_is_rejected_before_uniqueness_hides_it():
    # A single NaN key passes is_unique and merge matches NaN<->NaN, so a null
    # customer would silently join. Reject nulls explicitly (review High).
    feat, raw = _synthetic(3)
    feat.loc[0, "CLIENTNUM"] = None
    with pytest.raises(ValueError, match="CLIENTNUM must not contain nulls"):
        segment_profiles(feat, raw)


def test_null_segment_id_is_rejected_not_silently_dropped():
    # groupby drops the null group; a customer would vanish while n/share still
    # look plausible. Reject instead (review High - the most dangerous case).
    feat, raw = _synthetic(3)
    feat.loc[0, "segment_id"] = None
    with pytest.raises(ValueError, match="segment_id must not contain nulls"):
        segment_profiles(feat, raw)


def test_matched_customer_with_null_demographic_is_not_called_orphan():
    # A joined customer whose raw Customer_Age is null is a data-quality issue,
    # NOT a join failure. The orphan check (merge indicator) must not fire here
    # (review Med: the old null-value heuristic conflated the two).
    feat, raw = _synthetic(3)
    raw.loc[0, "Customer_Age"] = None
    prof = segment_profiles(feat, raw)  # must not raise "no matching raw row"
    assert prof["n"].sum() == len(feat)


def test_empty_features_is_rejected():
    feat, raw = _synthetic(3)
    with pytest.raises(ValueError, match="empty"):
        segment_profiles(feat.iloc[0:0], raw)


def test_real_leakage_columns_never_enter_the_profile():
    # The two target-correlated Naive_Bayes_Classifier_* columns, spelled in full,
    # must not surface in any profile output (whitelist keeps them out).
    feat, raw = _synthetic(4)
    leak = (
        "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
        "Dependent_count_Education_Level_Months_Inactive_12_mon_1",
        "Naive_Bayes_Classifier_Attrition_Flag_Card_Category_Contacts_Count_12_mon_"
        "Dependent_count_Education_Level_Months_Inactive_12_mon_2",
    )
    for col in leak:
        raw[col] = 0.5
    prof = segment_profiles(feat, raw)
    for col in leak:
        assert col not in prof.columns


# --- segment_attrition_rates (committed reproduction path for the report) -----

def test_attrition_rate_is_per_segment_fraction():
    # Fixture: only segment 4 has attrited customers (2 of 4 -> 0.5).
    feat, raw = _synthetic(4)
    rates = segment_attrition_rates(feat, raw)
    assert rates.loc[4] == pytest.approx(0.5)
    assert rates.loc[1] == pytest.approx(0.0)
    assert set(rates.index) == {1, 2, 3, 4}


def test_attrition_flag_is_not_in_the_demographic_profile():
    # Attrition_Flag is the 1-6 target; it must stay OUT of segment_profiles even
    # though segment_attrition_rates reports it separately (leakage hygiene).
    feat, raw = _synthetic(4)
    prof = segment_profiles(feat, raw)
    assert "Attrition_Flag" not in prof.columns


def test_report_persona_count_matches_segment_k():
    # AC3 is only honest if the report's persona count actually tracks
    # SEGMENT_K. If someone changes k=5 without rewriting the report, this fails
    # instead of the report silently claiming 4 personas for 5 segments
    # (review Med: the persona count was an operational hope, not a guarantee).
    import re
    from pathlib import Path

    from crm.config import SEGMENT_K

    report = (
        Path(__file__).resolve().parents[2]
        / "docs" / "implementation-artifacts" / "segment-profile-report-1-5.md"
    ).read_text(encoding="utf-8")
    personas = re.findall(r"^### 페르소나 \d+", report, flags=re.MULTILINE)
    assert len(personas) == SEGMENT_K
