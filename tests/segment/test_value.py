"""Behavioural tests for the single customer-value definition (story 1-2, AC1).

Why these assertions and not others
-----------------------------------
The tempting test is ``assert_series_equal(customer_value(df),
df["Total_Trans_Amt"].astype(float))``. That is a tautology: it re-implements
the function and agrees with itself, so a wrong definition passes as long as
the test copies the same wrongness. P1 story 2-2 shipped a sign-flip bug that
way.

So each test names a PROPERTY that AD-11 requires and that a plausible wrong
implementation would break:

  - dtype is float even though the real column is int64 (AC1 return contract)
  - raw scale is preserved - a normalised or log-transformed implementation
    changes the RATIO between two customers, so ratios are the probe
  - the caller's index survives, because consumers join on it
  - the input frame is not mutated (purity)
  - a missing column fails loudly and NAMES the column
"""

from __future__ import annotations

import pandas as pd
import pytest

from crm.segment.value import customer_value


def _frame(amounts: list[int], index: list[int] | None = None) -> pd.DataFrame:
    """A minimal BankChurners-shaped frame with the int64 dtype of real data.

    The index is assigned AFTER construction on purpose: handing the
    constructor both a ``pd.Series`` (carrying its own 0..n-1 index) and an
    ``index=`` argument makes pandas ALIGN rather than relabel, silently
    filling every row with NaN.
    """
    frame = pd.DataFrame(
        {
            "CLIENTNUM": list(range(len(amounts))),
            "Total_Trans_Amt": pd.Series(amounts, dtype="int64"),
        }
    )
    if index is not None:
        frame.index = pd.Index(index)
    return frame


def test_returns_float_dtype_from_int64_input() -> None:
    """AC1: the contract is Series[float]; real data ships int64."""
    result = customer_value(_frame([510, 3899, 18484]))

    assert result.dtype == "float64"


def test_preserves_raw_scale() -> None:
    """AD-11 raw-scale preservation, probed by ratio rather than by value.

    Normalisation (min-max, z-score) and log transforms all change the ratio
    between two customers. Equality of ratios therefore fails for every one of
    them while never restating the implementation.
    """
    result = customer_value(_frame([1000, 4000]))

    assert result.iloc[1] / result.iloc[0] == pytest.approx(4.0)


def test_preserves_magnitude_not_just_shape() -> None:
    """A ratio alone cannot catch a constant rescaling (e.g. amounts / 1000).

    Anchoring one known input to its output closes that gap without
    recomputing the transform for the whole column.
    """
    result = customer_value(_frame([510, 3899]))

    assert result.iloc[0] == pytest.approx(510.0)


def test_preserves_caller_index() -> None:
    """Consumers join on this index, so reindexing or sorting would corrupt them."""
    result = customer_value(_frame([300, 100, 200], index=[7, 3, 5]))

    assert list(result.index) == [7, 3, 5]


def test_does_not_reorder_values() -> None:
    """Sorting by value while keeping the index would silently mis-pair rows."""
    result = customer_value(_frame([300, 100, 200], index=[7, 3, 5]))

    assert list(result) == [300.0, 100.0, 200.0]


def test_does_not_mutate_input_frame() -> None:
    """Purity: the caller's frame is unchanged in dtype, shape and content."""
    df = _frame([510, 3899])
    before = df.copy(deep=True)

    customer_value(df)

    pd.testing.assert_frame_equal(df, before)


def test_result_is_not_a_view_into_the_input() -> None:
    """Mutating the output must not reach back into the caller's frame."""
    df = _frame([510, 3899])

    result = customer_value(df)
    result.iloc[0] = -1.0

    assert df["Total_Trans_Amt"].iloc[0] == 510


def test_missing_column_raises_naming_the_column() -> None:
    """A caller debugging this needs the column name, not just 'KeyError'."""
    df = pd.DataFrame({"CLIENTNUM": [1, 2]})

    with pytest.raises(KeyError, match="Total_Trans_Amt"):
        customer_value(df)


def test_empty_frame_with_the_column_returns_empty_float_series() -> None:
    """An empty-but-valid frame is not an error; the dtype contract still holds."""
    result = customer_value(_frame([]))

    assert len(result) == 0
    assert result.dtype == "float64"
