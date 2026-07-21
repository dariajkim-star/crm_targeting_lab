"""Segment profiles: who is in each segment (CAP-1, FR3).

Story 1-4 assigned every customer a value-ordered ``segment_id``, but the
demographic columns (age, gender, education, income, card tier, ...) live only
in the RAW BankChurners frame - ``features_customers`` carries just CLIENTNUM +
RFM + segment_id. So profiling JOINS the two on CLIENTNUM (both are the same
BankChurners lane, so this is not an AD-1 crossing).

This module is the COMMITTED, TESTED code path that makes the 1-5 report's
numbers reproducible (AC2): the report cites what these functions compute.

Consuming customer value (AD-11), not recomputing it. The only value figure
used is ``monetary_proxy`` from ``features`` - the persisted output of
``customer_value(df)`` (story 1-3). This module never names the value source
column, and the demographic columns it pulls from raw are an explicit WHITELIST
that excludes ``Total_Trans_Amt`` and the two leakage columns. CAP-5:
``Total_Revolving_Bal`` / ``Credit_Limit`` are profiling-only reference
indicators - shown here, never summed into value.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk.
Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import pandas as pd

__all__ = [
    "segment_profiles",
    "segment_category_shares",
    "PROFILE_NUMERIC_COLUMNS",
    "PROFILE_CATEGORICAL_COLUMNS",
]

_ID_COLUMN = "CLIENTNUM"
_SEGMENT_COLUMN = "segment_id"

# Value + behaviour figures taken from the FEATURES frame (monetary_proxy is the
# persisted customer_value output - consumed, never recomputed; AD-11).
_NUMERIC_FROM_FEATURES = ("monetary_proxy", "frequency_proxy", "recency_proxy")
# Demographic numerics pulled from RAW by explicit whitelist. Total_Trans_Amt and
# the Naive_Bayes_Classifier_* leakage columns are deliberately ABSENT (AD-11 /
# leakage). Credit_Limit and Total_Revolving_Bal are CAP-5 reference indicators.
_NUMERIC_FROM_RAW = (
    "Customer_Age",
    "Dependent_count",
    "Months_on_book",
    "Total_Relationship_Count",
    "Credit_Limit",
    "Total_Revolving_Bal",
    "Avg_Utilization_Ratio",
)
# Median is reported for these, in this order.
PROFILE_NUMERIC_COLUMNS = (*_NUMERIC_FROM_FEATURES, *_NUMERIC_FROM_RAW)

# Categorical demographics for share breakdowns. "Unknown" is a real category in
# several of these and is preserved, never dropped or imputed.
PROFILE_CATEGORICAL_COLUMNS = (
    "Gender",
    "Education_Level",
    "Marital_Status",
    "Income_Category",
    "Card_Category",
)


def _joined(features: pd.DataFrame, raw: pd.DataFrame, raw_columns: tuple[str, ...]) -> pd.DataFrame:
    """Left-join the requested raw columns onto the segmented customer set.

    Validates the join key so a duplicate/absent CLIENTNUM cannot silently
    corrupt a customer's profile (1-4 lesson: verify the key, do not assume it).
    """
    for frame, name, needed in (
        (features, "features", (_ID_COLUMN, _SEGMENT_COLUMN)),
        (raw, "raw", (_ID_COLUMN, *raw_columns)),
    ):
        missing = [c for c in needed if c not in frame.columns]
        if missing:
            raise KeyError(f"{name} frame is missing columns {missing}")

    if not features[_ID_COLUMN].is_unique:
        raise ValueError("features CLIENTNUM must be unique (one row per customer)")
    if not raw[_ID_COLUMN].is_unique:
        raise ValueError("raw CLIENTNUM must be unique (one row per customer)")

    merged = features.merge(
        raw[[_ID_COLUMN, *raw_columns]], on=_ID_COLUMN, how="left", validate="one_to_one"
    )
    orphans = merged[list(raw_columns)].isna().any(axis=1).sum() if raw_columns else 0
    if orphans:
        raise ValueError(
            f"{orphans} segmented customers have no matching raw row - the profile "
            f"would carry gaps. Reconcile CLIENTNUM between the two inputs."
        )
    return merged


def segment_profiles(features: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Per-segment summary: customer count, share, and numeric-metric medians.

    Pure. Returns a DataFrame indexed by ``segment_id`` (ascending) with columns
    ``n``, ``share`` (fractions summing to 1), then the median of every column in
    ``PROFILE_NUMERIC_COLUMNS``. Value figures come from ``monetary_proxy`` (AD-11
    consumption), never a recomputation.
    """
    merged = _joined(features, raw, _NUMERIC_FROM_RAW)
    grouped = merged.groupby(_SEGMENT_COLUMN, sort=True)

    profile = grouped[list(PROFILE_NUMERIC_COLUMNS)].median()
    profile.insert(0, "n", grouped.size())
    profile.insert(1, "share", profile["n"] / profile["n"].sum())
    return profile


def segment_category_shares(features: pd.DataFrame, raw: pd.DataFrame, column: str) -> pd.DataFrame:
    """Within-segment share of each category of ``column`` (rows sum to 1).

    Pure. Returns a DataFrame indexed by ``segment_id`` with one column per
    category; each row sums to 1. ``Unknown`` is treated as an ordinary category
    and is never dropped or imputed (honesty: the data's missingness is shown).
    """
    if column not in PROFILE_CATEGORICAL_COLUMNS:
        raise ValueError(
            f"{column!r} is not a profiled categorical column; choose from "
            f"{PROFILE_CATEGORICAL_COLUMNS}"
        )
    merged = _joined(features, raw, (column,))
    counts = (
        merged.groupby([_SEGMENT_COLUMN, column], sort=True).size().unstack(fill_value=0)
    )
    return counts.div(counts.sum(axis=1), axis=0)
