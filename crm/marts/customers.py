"""Assemble the customer mart by CLIENTNUM label join (AD-2, AD-12, story 4-1a).

THE JOB, AND THE ONE DEFECT IT EXISTS TO PREVENT
------------------------------------------------
Three upstream frames describe the same 10,127 customers: `bankchurners` (the
raw source, carries the value proxy), `features_customers` (segment_id + RFM),
and `churn_scored` (churn_score + churn_prob_calibrated + artifact_id). All three
are 10,127 rows, but IN DIFFERENT ROW ORDERS. Combining them by POSITION is
silently wrong and the project has already paid for it once:

    two parquet frames both carry a plain RangeIndex, so `bc.index.equals(sc.index)`
    returns True and a positional combine passes every guard - measured, the total
    expected saving came out 1,994,741 against the correct 1,454,088, +37.2%, with
    nothing raised (story 3-3 pre-investigation, "함정 4").

The only defence is to combine by LABEL. This module sets `CLIENTNUM` as the
shared index and requires the three CLIENTNUM sets to match EXACTLY - no subset,
no superset, no duplicate - before any axis is computed. Once every axis shares
one CLIENTNUM index, the partial CLIENTNUM guard already living in
`target_priority` (and the index-equality guards in `assign_quadrant` /
`expected_saving`) finally become effective: they can see a mis-join because the
index carries the customer identity, not a bare row number.

WHAT THIS MODULE DOES NOT DO (AD-9 / AD-11 / AD-12)
---------------------------------------------------
It computes no value, no cut, no saving, no rank of its own. `customer_value`,
`assign_quadrant` (labels AND thresholds from one computation), `expected_saving`
and `target_priority` are consumed exactly as the upstream lanes define them.
This module never names the value proxy column (AD-11): it hands the raw frame to
`customer_value`, which is the one place allowed to read it.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. The pipeline layer (`pipelines/05_marts.py`) owns I/O and calls
`assert_scored_identity` before assembling. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from crm.campaign.matrix import assign_quadrant
from crm.campaign.priority import PRIORITY_COLUMN, target_priority
from crm.campaign.simulate import SAVING_COLUMN, expected_saving
from crm.segment.value import customer_value

__all__ = [
    "MART_COLUMNS",
    "assert_scored_identity",
    "build_customer_mart",
    "serialize_mart",
]

_CLIENTNUM = "CLIENTNUM"
_SEGMENT_ID = "segment_id"
_VALUE = "customer_value"
_SCORE = "churn_score"
_PROB = "churn_prob_calibrated"
_QUADRANT = "quadrant_official"
_THRESH_RISK = "threshold_official_risk"
_THRESH_VALUE = "threshold_official_value"
_ID_COLUMN = "artifact_id"

# THE canonical column order. Single source of truth shared by the serialized CSV
# and `marts/mart_customers.schema.md` - a test asserts the schema doc lists
# exactly these, in this order (AC3, AC6). CLIENTNUM leads because it is the join
# key and the mart's identity; it is the frame's INDEX during assembly and is
# written back as the first COLUMN by `serialize_mart` (AC6 `index=False`).
MART_COLUMNS: tuple[str, ...] = (
    _CLIENTNUM,
    _SEGMENT_ID,
    _VALUE,
    _SCORE,
    _PROB,
    _QUADRANT,
    _THRESH_RISK,
    _THRESH_VALUE,
    SAVING_COLUMN,
    PRIORITY_COLUMN,
)

# Serialization contract (AC6, NFR4). Fixed so two runs are BYTE-IDENTICAL and a
# diff shows a real change, never a formatting drift. `float_format` touches only
# float columns, so the int columns (CLIENTNUM, segment_id, target_priority) keep
# their integer spelling; `na_rep` is defensive - the exact-set join leaves no
# gaps, but a fixed empty token means a future nullable column cannot silently
# introduce "nan" text.
_FLOAT_FORMAT = "%.6f"
_NA_REP = ""
_LINE_TERMINATOR = "\n"


def _index_by_clientnum(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Set CLIENTNUM as the index, refusing the shapes that would mis-join.

    A missing column, or a CLIENTNUM that repeats within one source, cannot be
    combined by label - the second would give the index duplicate labels and let
    a fan-out join count a customer twice. Both are named here rather than
    surfacing later as an opaque pandas alignment result.
    """
    if _CLIENTNUM not in frame.columns:
        raise ValueError(
            f"{source} has no '{_CLIENTNUM}' column, so the mart cannot be "
            f"assembled by label. A positional combine is exactly the +37.2% "
            f"defect this join exists to prevent (story 3-3 '함정 4')."
        )
    duplicated = frame[_CLIENTNUM].duplicated()
    if duplicated.any():
        raise ValueError(
            f"{source} carries duplicated {_CLIENTNUM} values "
            f"{frame.loc[duplicated, _CLIENTNUM].unique()[:5].tolist()}. "
            f"CLIENTNUM must identify one customer per row for a label join."
        )
    indexed = frame.set_index(_CLIENTNUM)
    indexed.index.name = _CLIENTNUM
    return indexed


def _require_identical_clientnum_sets(frames: dict[str, pd.DataFrame]) -> None:
    """Fail unless all three sources cover EXACTLY the same customers.

    Subset, superset and any disagreement all fail immediately (AC2). pandas
    would otherwise ALIGN the union and fill the gaps with NaN, turning a real
    coverage hole into plausible-looking rows the row-count assert might even
    accept. The reference is the first source's set; the message names what each
    other source is missing or carries extra so the fix is actionable.
    """
    names = list(frames)
    reference_name = names[0]
    reference = set(frames[reference_name].index)
    for other_name in names[1:]:
        other = set(frames[other_name].index)
        if other == reference:
            continue
        missing = sorted(reference - other)[:5]
        extra = sorted(other - reference)[:5]
        raise ValueError(
            f"CLIENTNUM sets differ between '{reference_name}' and "
            f"'{other_name}': '{other_name}' is missing {missing} and carries "
            f"extra {extra}. The three sources must describe the same customers "
            f"exactly - a label join over mismatched sets would fabricate or "
            f"drop rows."
        )


def build_customer_mart(
    bankchurners: pd.DataFrame,
    features: pd.DataFrame,
    scored: pd.DataFrame,
) -> pd.DataFrame:
    """Assemble the customer mart, indexed by CLIENTNUM (AC1, AC2, AC4).

    Args:
        bankchurners: The raw BankChurners frame (story 1-1b), carrying the value
            proxy column consumed by `customer_value`. Must carry `CLIENTNUM`.
        features: `features_customers` (story 1-4), carrying `segment_id`.
        scored: `churn_scored` (story 3-0), carrying `churn_score`,
            `churn_prob_calibrated` and `artifact_id`.

    Returns:
        A frame indexed by `CLIENTNUM` (int64, unique) carrying every mart column
        except CLIENTNUM itself (which is the index), in `MART_COLUMNS[1:]` order.
        `serialize_mart` writes CLIENTNUM back as the leading column.

    Raises:
        ValueError: on a missing/duplicated CLIENTNUM in any source, on CLIENTNUM
            sets that do not match exactly, or from any consumed function whose
            precondition the assembled axes violate (a null, a negative value,
            a wrong probability column name).
    """
    bc = _index_by_clientnum(bankchurners, "bankchurners")
    ft = _index_by_clientnum(features, "features_customers")
    sc = _index_by_clientnum(scored, "churn_scored")
    _require_identical_clientnum_sets({"bankchurners": bc, "features_customers": ft, "churn_scored": sc})

    # Reindex the other two onto bankchurners' order so every axis below shares
    # ONE CLIENTNUM index in ONE order. The set check above guarantees this is a
    # pure reordering (no NaN introduced) - reindex is the label join made
    # explicit, and it is what makes the downstream index guards effective.
    ft = ft.reindex(bc.index)
    sc = sc.reindex(bc.index)

    # Every axis is indexed by CLIENTNUM, so the consumed functions' index-equality
    # and CLIENTNUM guards all fire on a real mis-join instead of a bare RangeIndex.
    value = customer_value(bc).rename(_VALUE)
    churn_score = sc[_SCORE]
    churn_prob = sc[_PROB]
    assignment = assign_quadrant(churn_score, value)
    saving = expected_saving(churn_prob, value)
    clientnum = pd.Series(bc.index.to_numpy(), index=bc.index, name=_CLIENTNUM)
    priority = target_priority(saving, value, clientnum)

    # Built column-by-column from Series that share bc.index, so pandas aligns by
    # CLIENTNUM (not position). Scalars broadcast. Column order is MART_COLUMNS
    # minus the leading CLIENTNUM, which is the index.
    mart = pd.DataFrame(
        {
            _SEGMENT_ID: ft[_SEGMENT_ID],
            _VALUE: value,
            _SCORE: churn_score,
            _PROB: churn_prob,
            _QUADRANT: assignment.labels,
            _THRESH_RISK: assignment.thresholds.risk,
            _THRESH_VALUE: assignment.thresholds.value,
            SAVING_COLUMN: saving,
            PRIORITY_COLUMN: priority,
        }
    )
    mart.index.name = _CLIENTNUM

    # Canonical row order = CLIENTNUM ascending. The label join already puts the
    # RIGHT value on each customer's row whatever order the inputs arrive in;
    # sorting makes the SERIALIZED bytes a function of content alone, so a future
    # upstream reshuffle (a reordered 03 rerun, a parallel write) cannot change
    # the mart's bytes without changing its data. target_priority is a per-customer
    # rank and is unaffected by row order. This turns AC6 determinism from
    # "same input file" into "same input content" (strictly stronger).
    mart = mart.sort_index()

    # AC4: no sentinel, no dropped rows. The exact-set join leaves no gaps, but
    # the assert is kept as a contract - a future nullable column must announce
    # itself here rather than serialize a blank the schema calls non-nullable.
    null_columns = [column for column in mart.columns if mart[column].isna().any()]
    if null_columns:
        raise ValueError(
            f"mart columns carry nulls {null_columns}; the mart is non-nullable "
            f"by contract (AC4). Missing values are a broken upstream join, not "
            f"a cell to leave blank."
        )
    return mart[list(MART_COLUMNS[1:])]


def serialize_mart(mart: pd.DataFrame) -> bytes:
    """Serialize the mart to deterministic CSV bytes (AC6, NFR4).

    CLIENTNUM moves from the index to the leading column (`reset_index`), the
    columns are pinned to `MART_COLUMNS`, and the six serialization knobs are
    fixed: `index=False`, the float format, the empty NA token, UTF-8 without a
    BOM, and a `\\n` line terminator. Two runs on the same frame produce
    byte-identical output.
    """
    ordered = mart.reset_index()[list(MART_COLUMNS)]
    text = ordered.to_csv(
        index=False,
        na_rep=_NA_REP,
        float_format=_FLOAT_FORMAT,
        lineterminator=_LINE_TERMINATOR,
    )
    # UTF-8 with no BOM. `str.encode("utf-8")` never emits a BOM (unlike
    # "utf-8-sig"), which is the spelling AC6 requires.
    return text.encode("utf-8")


def assert_scored_identity(scored: pd.DataFrame, model_path: Path) -> str:
    """Fail unless the scores describe the model on disk (AC5, AD-5).

    The mart carries `churn_score` and `churn_prob_calibrated`; this gate proves
    which training run they belong to. It CONSUMES the churn identity contract
    rather than re-deriving it: `read_verified_model_meta` is the function AD-5
    names for the 4-1 mart to call (it also proves the record describes the
    `.joblib` actually on disk), and `verify_artifact_identity` raises - not
    warns - on a mismatch, because a mart built on scores from a different model
    is silently wrong.

    Imported lazily so this module stays importable without the churn model
    stack (xgboost/joblib): only the pipeline, running against real artifacts,
    exercises the gate. The lane guard still sees the import (it is AST-based and
    walks function bodies) and `crm.churn.*` is a permitted Lane A dependency.

    Returns the verified artifact_id. Raises ValueError if the scored frame
    carries no single usable artifact_id, or ArtifactIdentityError on a mismatch
    or a missing/unreadable model record.
    """
    # Validate the frame BEFORE importing the churn stack: an obviously-broken
    # scored frame (no id column, or several ids) should fail without paying the
    # model-import cost, and it keeps these branches testable in environments
    # without xgboost installed.
    if _ID_COLUMN not in scored.columns:
        raise ValueError(
            f"churn_scored has no '{_ID_COLUMN}' column - it cannot be gated "
            f"against the model identity (AD-5)."
        )
    ids = scored[_ID_COLUMN].dropna().unique()
    if len(ids) != 1:
        raise ValueError(
            f"churn_scored carries {len(ids)} distinct {_ID_COLUMN} values; a "
            f"single training run must stamp exactly one. Rerun 03_train_churn."
        )
    stamped = str(ids[0])

    from crm.churn.artifact import read_verified_model_meta, verify_artifact_identity

    expected = read_verified_model_meta(model_path)[_ID_COLUMN]
    verify_artifact_identity(expected, stamped, context="churn_scored.parquet")
    return expected
