"""K-means segmentation with value-ordered stable IDs (CAP-1, AD-7).

The raw K-means label is an arbitrary integer that changes run to run and seed
to seed. Committing it would let "segment 3" silently point at a different group
on the next run - the exact accident AD-7 exists to prevent. So this module
NORMALISES the labels into a stable ``segment_id`` 1..k by reordering clusters
on descending median customer value: segment 1 is always the highest-value tier.

Consuming customer value (AD-11), not recomputing it. The value used for the
reorder is the ``monetary_proxy`` column, which story 1-3 wrote as the persisted
output of ``customer_value(df)``. Reading that column is CONSUMPTION of the 1-2
function's output, not a recomputation, and it never names the value source
column - so the AD-11 guard (find_value_recomputation_violations) is satisfied
without exception.

Determinism (AD-7). ``KMeans`` receives ``random_state`` and an explicit
``n_init`` from RANDOM_SEED (sklearn >= 1.4 defaults n_init to "auto", which AD-7
forbids relying on). ``StandardScaler`` is deterministic. The reorder breaks
median ties by a total order (median -> mean -> raw label) so two consecutive
runs assign byte-identical ``segment_id``.

Scaling here is clustering pre-processing, NOT value-axis normalisation: monetary
spans thousands and would dominate Euclidean distance unscaled. This is the
scaling AD-11 permits inside a consuming step; the mart still stores raw value.

Purity (AD-1/AD-9): the input frame is never modified, nothing is written to
disk, no global state is touched. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from crm.config import RANDOM_SEED, SEGMENT_K
from crm.segment.features import RFM_OUTPUT_COLUMNS, compute_rfm_features

__all__ = [
    "assign_segments",
    "build_feature_table",
    "CLUSTERING_FEATURES",
    "FEATURE_TABLE_COLUMNS",
]

# The 02_features stage output contract: the 1-3 RFM columns plus segment_id.
# Downstream (1-5 profiles, 4-1 mart) references this instead of hardcoding.
FEATURE_TABLE_COLUMNS = (*RFM_OUTPUT_COLUMNS, "segment_id")

# Join key + canonical sort key (unique per customer) for order-invariant fits.
_ID_COLUMN = "CLIENTNUM"
# The value axis used to order segments high-to-low. This is the persisted
# customer_value output (story 1-3), consumed - not recomputed (AD-11).
_VALUE_COLUMN = "monetary_proxy"
# Raw RFM proxies clustered on (standardised). Scores (1..5) are coarser - R has
# only 4 levels on the real data - so the raw proxies carry more signal.
CLUSTERING_FEATURES = ("recency_proxy", "frequency_proxy", "monetary_proxy")

# Explicit, fixed n_init (AD-7): never lean on sklearn's "auto" default.
_N_INIT = 10


def assign_segments(features: pd.DataFrame, k: int = SEGMENT_K, seed: int = RANDOM_SEED) -> pd.Series:
    """Return a value-ordered ``segment_id`` (1..k) Series indexed like ``features``.

    Pure and index-preserving: ``features`` is untouched, rows are neither sorted
    nor reindexed, and the returned Series carries the input index for a
    row-for-row join.

    Args:
        features: RFM feature table (story 1-3 schema) with CLUSTERING_FEATURES
            and the persisted ``monetary_proxy`` value column.
        k: number of clusters (default from config; chosen in the 1-4 report).
        seed: RANDOM_SEED, injected into KMeans for determinism.

    Returns:
        ``Series[int]`` of segment_id 1..k, 1 = highest median customer value.

    Raises:
        KeyError: naming any required column that is absent.
        ValueError: if ``k`` is out of range for the data (k < 2 or k > n rows).
    """
    missing = [c for c in (_ID_COLUMN, *CLUSTERING_FEATURES, _VALUE_COLUMN) if c not in features.columns]
    if missing:
        raise KeyError(f"assign_segments requires columns {missing}; they are absent.")
    if k < 2:
        raise ValueError(f"k must be >= 2 to form segments, got {k}")
    if k > len(features):
        raise ValueError(f"k={k} exceeds the number of rows ({len(features)})")

    # Cluster on a CANONICAL row order (by CLIENTNUM), not the caller's order.
    # KMeans is order-sensitive - k-means++ init samples points in data order -
    # so without this a shuffled frame yields different labels for the same
    # customers. Sorting first makes segment_id invariant to input row order
    # (AD-7 in spirit; the pipeline's fixed read order already gives run-to-run
    # determinism, this hardens it against any caller reordering).
    canonical = features.sort_values(_ID_COLUMN)
    scaled = StandardScaler().fit_transform(canonical[list(CLUSTERING_FEATURES)])
    labels = pd.Series(
        KMeans(n_clusters=k, random_state=seed, n_init=_N_INIT).fit_predict(scaled),
        index=canonical.index,
    )

    # Rank clusters by descending median value (total-order tiebreak so ties do
    # not make the labelling depend on run-to-run cluster numbering).
    stats = (
        pd.DataFrame({"label": labels.to_numpy(), "value": canonical[_VALUE_COLUMN].to_numpy()})
        .groupby("label", sort=True)["value"]
        .agg(["median", "mean"])
    )
    order = stats.sort_values(
        ["median", "mean", "label"], ascending=[False, False, True]
    ).index.to_numpy()
    # order[0] is the highest-value cluster -> segment_id 1.
    label_to_segment = {int(label): rank + 1 for rank, label in enumerate(order)}

    # Map back and restore the caller's original row order.
    return labels.map(label_to_segment).reindex(features.index).astype(int)


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    """Assemble the full 02_features output: RFM proxies + segment_id.

    Keeps the pipeline stage thin (AD-9): the stage calls this one function
    rather than orchestrating RFM and segmentation itself. compute_rfm_features
    stays RFM-only (story 1-3); segmentation is layered on here.
    """
    features = compute_rfm_features(df)
    features = features.assign(segment_id=assign_segments(features))
    return features[list(FEATURE_TABLE_COLUMNS)]
