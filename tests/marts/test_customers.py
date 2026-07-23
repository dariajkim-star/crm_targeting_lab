"""Behavioural tests for the customer mart (story 4-1a).

Why these assertions and not others (P1 2-2 sign-flip lesson: never re-implement
the formula and compare it to itself):

  - TRAP 4 (AC2) is the reason this story exists. The test feeds the three
    sources in DIFFERENT row orders and pins two facts at once: the label join
    puts each customer's OWN value/probability on their row, and a POSITIONAL
    combine of the same shuffled frames would produce a DIFFERENT total. The
    second half is what proves the first is not an accident of ordering.
  - DETERMINISM (AC6) is checked as byte-identity of the serialized CSV, and
    checked to survive an input reshuffle - the property the canonical sort buys.
  - SCHEMA (AC3) is checked against `mart_customers.schema.md` itself, so the doc
    and the frame cannot drift apart; the doc is the single source of column order.
  - EXACT-SET join (AC2) and ROW PRESERVATION (AC4) are pinned by their failure
    modes: a subset, a superset and a duplicate each raise, and the mart carries
    no nulls.

Fixtures are synthetic and tiny so the expected values are hand-computable. The
real-data oracle at the bottom skips when the parquet artifacts are absent
(3-4 convention).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crm.config import COST_PER_CONTACT, RETENTION_SUCCESS_RATE
from crm.marts.customers import (
    MART_COLUMNS,
    assert_scored_identity,
    build_customer_mart,
    serialize_mart,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SCHEMA_DOC = REPO_ROOT / "marts" / "mart_customers.schema.md"

# Six customers with DISTINCT values and probabilities, so any misalignment of
# probability against value changes the total (the trap-4 signal). Risk scores
# stay in [0, 1] for assign_quadrant. CLIENTNUMs are deliberately NOT in sorted
# order, so the canonical-sort behaviour is visible.
_CLIENTNUMS = [503, 101, 407, 202, 306, 605]
_VALUE = [1000, 4000, 2000, 5000, 3000, 6000]  # Total_Trans_Amt (int, raw scale)
_PROB = [0.10, 0.40, 0.20, 0.50, 0.30, 0.60]  # calibrated churn probability
_SCORE = [0.15, 0.45, 0.25, 0.55, 0.35, 0.65]  # raw OOF ranking score
_SEGMENT = [0, 1, 2, 3, 0, 1]


def _sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """The three upstream frames, each in its OWN row order (trap-4 setup)."""
    bankchurners = pd.DataFrame({"CLIENTNUM": _CLIENTNUMS, "Total_Trans_Amt": _VALUE})
    features = pd.DataFrame({"CLIENTNUM": _CLIENTNUMS, "segment_id": _SEGMENT})
    scored = pd.DataFrame(
        {
            "CLIENTNUM": _CLIENTNUMS,
            "churn_score": np.array(_SCORE, dtype="float32"),
            "churn_prob_calibrated": _PROB,
            "artifact_id": "a" * 64,
        }
    )
    # Shuffle each source to a DIFFERENT permutation. If the join were positional,
    # customer 503's value would be paired with some other customer's probability.
    return (
        bankchurners.sample(frac=1, random_state=1).reset_index(drop=True),
        features.sample(frac=1, random_state=2).reset_index(drop=True),
        scored.sample(frac=1, random_state=3).reset_index(drop=True),
    )


def _expected_saving(prob: float, value: float) -> float:
    return prob * value * RETENTION_SUCCESS_RATE - COST_PER_CONTACT


# --- AC2: CLIENTNUM label join defeats trap 4 --------------------------------


def test_join_is_by_label_each_customer_keeps_own_axes() -> None:
    """The heart of the story: value and probability meet on CLIENTNUM, not row."""
    mart = build_customer_mart(*_sources())

    for clientnum, value, prob in zip(_CLIENTNUMS, _VALUE, _PROB):
        row = mart.loc[clientnum]
        assert row["customer_value"] == pytest.approx(value)
        assert row["expected_saving"] == pytest.approx(_expected_saving(prob, value))


def test_positional_combine_would_have_produced_a_different_total() -> None:
    """Prove the label join is not an accident of ordering (trap-4 regression).

    The correct total is sum(prob_i * value_i) over each customer's OWN axes. A
    positional combine of the shuffled frames pairs each row's value with
    whatever probability sits at the same POSITION in the (differently shuffled)
    scored frame - a different sum. The mart must equal the first and not the
    second.
    """
    bankchurners, _features, scored = _sources()
    mart = build_customer_mart(*_sources())

    correct_total = sum(_expected_saving(prob, value) for prob, value in zip(_PROB, _VALUE))
    positional_total = float(
        (
            scored["churn_prob_calibrated"].to_numpy() * bankchurners["Total_Trans_Amt"].to_numpy()
            * RETENTION_SUCCESS_RATE
            - COST_PER_CONTACT
        ).sum()
    )

    assert mart["expected_saving"].sum() == pytest.approx(correct_total)
    # The setup is only meaningful if the two totals actually differ - guard the
    # guard, so a fixture that accidentally aligned could never pass silently.
    assert correct_total != pytest.approx(positional_total)
    assert mart["expected_saving"].sum() != pytest.approx(positional_total)


def test_mismatched_clientnum_sets_fail_fast() -> None:
    bankchurners, features, scored = _sources()
    short = scored.iloc[1:].reset_index(drop=True)  # drop one customer

    with pytest.raises(ValueError, match="CLIENTNUM sets differ"):
        build_customer_mart(bankchurners, features, short)


def test_superset_also_fails() -> None:
    bankchurners, features, scored = _sources()
    extra = pd.concat(
        [bankchurners, pd.DataFrame({"CLIENTNUM": [999], "Total_Trans_Amt": [100]})],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="CLIENTNUM sets differ"):
        build_customer_mart(extra, features, scored)


def test_duplicate_clientnum_within_a_source_fails() -> None:
    bankchurners, features, scored = _sources()
    dup = pd.concat([bankchurners, bankchurners.iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicated CLIENTNUM"):
        build_customer_mart(dup, features, scored)


def test_missing_clientnum_column_names_the_source() -> None:
    bankchurners, features, scored = _sources()
    no_key = bankchurners.rename(columns={"CLIENTNUM": "id"})

    with pytest.raises(ValueError, match="bankchurners has no 'CLIENTNUM'"):
        build_customer_mart(no_key, features, scored)


# --- AC4: row preservation, no nulls -----------------------------------------


def test_all_rows_preserved_and_no_nulls() -> None:
    mart = build_customer_mart(*_sources())

    assert len(mart) == len(_CLIENTNUMS)
    assert set(mart.index) == set(_CLIENTNUMS)
    assert mart.index.name == "CLIENTNUM"
    assert mart.index.is_unique
    assert int(mart.isna().sum().sum()) == 0


def test_target_priority_is_a_total_order_over_everyone() -> None:
    """Every customer ranked exactly once, 1..n - including negative savings."""
    mart = build_customer_mart(*_sources())

    assert sorted(mart["target_priority"].tolist()) == list(range(1, len(_CLIENTNUMS) + 1))


# --- AC6: deterministic, byte-identical serialization ------------------------


def test_serialization_is_byte_identical_across_builds() -> None:
    first = serialize_mart(build_customer_mart(*_sources()))
    second = serialize_mart(build_customer_mart(*_sources()))

    assert first == second


def test_serialization_survives_input_reshuffle() -> None:
    """Canonical CLIENTNUM sort makes the bytes a function of content, not order.

    Two independent shuffles of the SAME data must serialize identically - the
    property that turns AC6 from 'same input file' into 'same input content'.
    """
    bankchurners = pd.DataFrame({"CLIENTNUM": _CLIENTNUMS, "Total_Trans_Amt": _VALUE})
    features = pd.DataFrame({"CLIENTNUM": _CLIENTNUMS, "segment_id": _SEGMENT})
    scored = pd.DataFrame(
        {
            "CLIENTNUM": _CLIENTNUMS,
            "churn_score": np.array(_SCORE, dtype="float32"),
            "churn_prob_calibrated": _PROB,
        }
    )
    order_a = serialize_mart(
        build_customer_mart(
            bankchurners.sample(frac=1, random_state=7).reset_index(drop=True),
            features.sample(frac=1, random_state=8).reset_index(drop=True),
            scored.sample(frac=1, random_state=9).reset_index(drop=True),
        )
    )
    order_b = serialize_mart(
        build_customer_mart(
            bankchurners.sample(frac=1, random_state=11).reset_index(drop=True),
            features.sample(frac=1, random_state=12).reset_index(drop=True),
            scored.sample(frac=1, random_state=13).reset_index(drop=True),
        )
    )

    assert order_a == order_b


def test_serialized_bytes_meet_the_fixed_format() -> None:
    """The six knobs AC6 fixes: header order, CLIENTNUM first, \\n, no BOM, %.6f."""
    raw = serialize_mart(build_customer_mart(*_sources()))

    assert not raw.startswith(b"\xef\xbb\xbf")  # no UTF-8 BOM
    assert b"\r\n" not in raw  # \n only
    text = raw.decode("utf-8")
    lines = text.split("\n")
    assert lines[0] == ",".join(MART_COLUMNS)  # header = canonical order, CLIENTNUM first
    assert text.endswith("\n")
    # Rows are CLIENTNUM-ascending, and CLIENTNUM stays an integer (float_format
    # must not touch int columns).
    data_clientnums = [int(line.split(",")[0]) for line in lines[1:] if line]
    assert data_clientnums == sorted(_CLIENTNUMS)
    # A float column carries exactly six decimals.
    value_cell = lines[1].split(",")[MART_COLUMNS.index("customer_value")]
    assert value_cell.split(".")[1] == "000000"


# --- AC3: the schema doc is the single source of columns ---------------------


def _schema_columns() -> list[tuple[str, str]]:
    """Parse (name, dtype) rows from the column table in the schema doc."""
    known = set(MART_COLUMNS)
    rows: list[tuple[str, str]] = []
    for line in SCHEMA_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        name = cells[0].strip("`")
        if name in known:
            rows.append((name, cells[1].split()[0]))  # dtype's first token
    return rows


def test_schema_doc_lists_exactly_the_mart_columns_in_order() -> None:
    names = [name for name, _dtype in _schema_columns()]

    assert tuple(names) == MART_COLUMNS


def test_mart_columns_and_dtypes_match_the_schema_doc() -> None:
    """set(df.columns) == schema.columns AND dtype agreement (AC3)."""
    frame = build_customer_mart(*_sources()).reset_index()[list(MART_COLUMNS)]
    schema = dict(_schema_columns())

    assert set(frame.columns) == set(schema)
    for column in frame.columns:
        assert str(frame[column].dtype) == schema[column], (
            f"{column}: frame is {frame[column].dtype}, schema says {schema[column]}"
        )


# --- AC5: artifact_id identity gate (frame-side branches, no model needed) ----


def test_gate_rejects_missing_artifact_id_column() -> None:
    scored = pd.DataFrame({"CLIENTNUM": _CLIENTNUMS})

    with pytest.raises(ValueError, match="no 'artifact_id' column"):
        assert_scored_identity(scored, DATA_DIR / "nonexistent_model.joblib")


def test_gate_rejects_multiple_artifact_ids() -> None:
    scored = pd.DataFrame(
        {"CLIENTNUM": [1, 2], "artifact_id": ["a" * 64, "b" * 64]}
    )

    with pytest.raises(ValueError, match="distinct artifact_id"):
        assert_scored_identity(scored, DATA_DIR / "nonexistent_model.joblib")


# --- Real-data oracle (skips without the artifacts; 3-4 convention) ----------


def _real_sources_available() -> bool:
    return all(
        (DATA_DIR / name).exists()
        for name in ("bankchurners.parquet", "features_customers.parquet", "churn_scored.parquet")
    )


@pytest.mark.skipif(not _real_sources_available(), reason="real parquet artifacts absent")
def test_real_data_mart_preserves_base_and_reproduces_correct_total() -> None:
    """On the real artifact: 10,127 rows and the CORRECT (label-joined) total.

    The number that matters is 1,454,088 - the +37.2% figure (1,994,741) is what
    a positional combine produced, so hitting the correct total end-to-end is the
    trap-4 defence proven on production data.
    """
    bankchurners = pd.read_parquet(DATA_DIR / "bankchurners.parquet")
    features = pd.read_parquet(DATA_DIR / "features_customers.parquet")
    scored = pd.read_parquet(DATA_DIR / "churn_scored.parquet")

    mart = build_customer_mart(bankchurners, features, scored)

    assert len(mart) == 10127
    assert int(mart.isna().sum().sum()) == 0
    assert sorted(mart["target_priority"].tolist()) == list(range(1, 10128))
    assert mart["expected_saving"].sum() == pytest.approx(1454088, abs=1.0)
    # Byte-identity across two independent builds on the real frame (AC6).
    assert serialize_mart(mart) == serialize_mart(build_customer_mart(bankchurners, features, scored))
