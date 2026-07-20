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


def test_preserves_every_value_across_the_observed_range() -> None:
    """A hardcoded oracle spanning the real data range (510 .. 18,484).

    Avoiding tautology means not RECOMPUTING the transform in the test. It does
    not mean avoiding a fixed expected result. Property probes alone left real
    gaps: upper clipping, a piecewise rescale that only touches large values,
    and NaN-to-zero substitution all passed the property tests, because those
    tests only ever looked at small values, two ratios and one anchor.

    This oracle is written out by hand, so a wrong implementation cannot agree
    with it by sharing the same mistake.
    """
    df = _frame([0, 510, 3899, 4000, 10000, 18484], index=[9, 2, 7, 1, 8, 3])
    expected = pd.Series(
        [0.0, 510.0, 3899.0, 4000.0, 10000.0, 18484.0],
        index=pd.Index([9, 2, 7, 1, 8, 3]),
        dtype="float64",
        name=None,
    )

    pd.testing.assert_series_equal(customer_value(df), expected)


def test_preserves_missing_values() -> None:
    """Missing must stay missing - substituting 0 would invent a customer.

    A zero-filled value is not a neutral default here: it places the customer
    at the bottom of the value axis, which is a fabricated business fact.
    Real BankChurners has no missing values in this column, so nothing in the
    real-data run would ever reveal the substitution.
    """
    df = pd.DataFrame({"Total_Trans_Amt": pd.Series([510.0, float("nan"), 18484.0])})

    result = customer_value(df)

    assert result.iloc[0] == pytest.approx(510.0)
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == pytest.approx(18484.0)


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


def test_result_mutation_does_not_modify_input() -> None:
    """Mutating the output must not reach back into the caller's frame.

    Named for the BEHAVIOUR, not for a memory layout: under pandas 3.x
    Copy-on-Write the result may legitimately be a lazy view, so asserting
    "is not a view" would be testing an implementation detail that the
    contract does not promise.
    """
    df = _frame([510, 3899])

    result = customer_value(df)
    result.iloc[0] = -1.0

    assert df["Total_Trans_Amt"].iloc[0] == 510


def test_result_mutation_does_not_modify_float_input() -> None:
    """The same guarantee when NO dtype conversion is needed.

    With int64 input the float cast has to produce a new numeric buffer, so
    non-aliasing holds for a reason unrelated to the contract. A float64 input
    exercises the same-dtype path, which is the one that actually depends on
    the Copy-on-Write guarantee.
    """
    df = pd.DataFrame({"Total_Trans_Amt": pd.Series([510.0, 3899.0], dtype="float64")})

    result = customer_value(df)
    result.iloc[0] = -1.0

    assert df["Total_Trans_Amt"].iloc[0] == pytest.approx(510.0)


def test_duplicate_value_columns_fail_loudly() -> None:
    """pandas allows duplicate labels; df[col] then yields a DataFrame.

    Without this check the Series return contract breaks and the caller sees an
    opaque pandas TypeError instead of the actual problem.
    """
    df = pd.DataFrame([[510, 999]], columns=["Total_Trans_Amt", "Total_Trans_Amt"])

    with pytest.raises(ValueError, match="exactly one"):
        customer_value(df)


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
