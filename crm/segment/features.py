"""RFM proxy features for the BankChurners lane (CAP-1, FR1).

BankChurners has no purchase-event log, so the three RFM axes are PROXIES built
from the summary columns the dataset does carry:

    R (Recency)   <- Months_Inactive_12_mon   (POLARITY INVERTED, see below)
    F (Frequency) <- Total_Trans_Ct
    M (Monetary)  <- customer_value(df)        (NOT the raw column - see AD-11)

Two deliberate design points a reader must not "fix" by accident:

1. AD-11 name ownership. The monetary axis IS the customer-value axis, and only
   ``crm/segment/value.py`` may name the column behind it. This module therefore
   consumes ``customer_value(df)`` and never spells the value column - that is
   the wiring AD-11 intends, not a way around the guard
   (``find_value_recomputation_violations`` enforces it).

2. Recency polarity. ``Months_Inactive_12_mon`` grows as a customer becomes LESS
   recent. The recency SCORE therefore inverts it: fewer inactive months -> more
   recent -> higher R score. A non-inverted recency score would rank the most
   dormant customers as the most engaged - the exact sign error P1 2-2 shipped.

Binning (AD-1, AD-7). Scores are quantile buckets computed from the BankChurners
frame at runtime; no edge is ever hardcoded in ``crm/config.py`` (parking a
data-derived value there would leak across lanes, AD-1). ``pd.qcut`` is
deterministic on fixed data (AD-7). ``Months_Inactive_12_mon`` has only 7
distinct integer levels heavily massed on 1/2/3, so a 5-quantile cut collapses
to fewer buckets; ``duplicates="drop"`` accepts the achieved bucket count rather
than crashing, and the recency score consequently has coarser resolution than F
and M. That is a property of the data, recorded in rfm-proxy-report-1-3.md, not
a defect to paper over.

Purity (AD-1/AD-9): the input frame is never modified, nothing is written to
disk, no global state is touched. The pipeline layer owns I/O.

Encoding note: runtime strings stay ASCII (Windows cp949 console).
"""

from __future__ import annotations

import pandas as pd

from crm.config import RFM_QUANTILES
from crm.segment.value import customer_value

__all__ = ["compute_rfm_features", "RFM_OUTPUT_COLUMNS"]

# Join key carried through so 1-4 (K-means) and 1-6 (churn) can align rows.
_ID_COLUMN = "CLIENTNUM"
# Recency proxy source. Higher = LESS recent (inverted when scored).
_RECENCY_SOURCE = "Months_Inactive_12_mon"
# Frequency proxy source: 12-month transaction count.
_FREQUENCY_SOURCE = "Total_Trans_Ct"

# The exact columns this stage emits. Naming the set explicitly is what keeps
# the two Naive_Bayes_Classifier_* leakage columns (target-correlated +/-1.0000)
# out of the feature table: they are never selected, and a test asserts it
# (AC5). 1-6's leakage audit re-confirms; this is the first line of defence.
RFM_OUTPUT_COLUMNS = (
    _ID_COLUMN,
    "recency_proxy",
    "frequency_proxy",
    "monetary_proxy",
    "R_score",
    "F_score",
    "M_score",
)


def _quantile_score(series: pd.Series, quantiles: int, invert: bool) -> pd.Series:
    """Bucket ``series`` into quantile scores 1..k (k = achieved bucket count).

    Deterministic: ``pd.qcut`` on a fixed distribution always draws the same
    edges (AD-7). ``duplicates="drop"`` means a degenerate distribution yields
    FEWER than ``quantiles`` buckets instead of raising - the caller documents
    the achieved resolution rather than pretending five clean quintiles exist.

    ``invert`` flips the ranking within the achieved range (for recency, where a
    smaller raw value means a higher score).
    """
    # cat.codes is 0-based in ascending value order; +1 makes scores 1-based.
    codes = pd.qcut(series, quantiles, duplicates="drop").cat.codes
    scores = codes + 1
    if invert:
        # Reflect within the achieved bucket count so scores stay 1..k with no
        # gaps regardless of how many buckets survived the duplicate drop.
        achieved = int(codes.max()) + 1
        scores = (achieved + 1) - scores
    return scores.astype(int)


def compute_rfm_features(df: pd.DataFrame, quantiles: int = RFM_QUANTILES) -> pd.DataFrame:
    """Return the RFM proxy feature table for a BankChurners-shaped frame.

    Pure and index-preserving: the returned frame carries the same index as
    ``df`` (rows are neither sorted nor reindexed) and ``df`` itself is untouched.

    Args:
        df: BankChurners frame with ``CLIENTNUM``, ``Months_Inactive_12_mon``,
            ``Total_Trans_Ct`` and the value column ``customer_value`` reads.
        quantiles: target quantile count for scoring (default from config).

    Returns:
        DataFrame with columns ``RFM_OUTPUT_COLUMNS``, indexed like ``df``.

    Raises:
        KeyError: naming every required source column that is absent, so the
            caller can act without reading this source.
    """
    required = (_ID_COLUMN, _RECENCY_SOURCE, _FREQUENCY_SOURCE)
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise KeyError(
            f"compute_rfm_features requires columns {missing} for the RFM proxies "
            f"and they are absent from the frame passed in."
        )

    # Monetary axis is the customer-value axis: CONSUME value.py, never name the
    # column (AD-11). customer_value preserves df's index, so the assembled frame
    # aligns row-for-row without a join.
    monetary = customer_value(df)

    features = pd.DataFrame(
        {
            _ID_COLUMN: df[_ID_COLUMN],
            "recency_proxy": df[_RECENCY_SOURCE],
            "frequency_proxy": df[_FREQUENCY_SOURCE],
            "monetary_proxy": monetary,
            "R_score": _quantile_score(df[_RECENCY_SOURCE], quantiles, invert=True),
            "F_score": _quantile_score(df[_FREQUENCY_SOURCE], quantiles, invert=False),
            "M_score": _quantile_score(monetary, quantiles, invert=False),
        },
        index=df.index,
    )
    return features[list(RFM_OUTPUT_COLUMNS)]
