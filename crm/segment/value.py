"""The single definition of customer value (AD-11).

THIS MODULE IS THE ONLY PLACE CUSTOMER VALUE IS DEFINED.

The 2x2 quadrant assignment, the expected-savings simulator, the sensitivity
sweep and the customer mart all CONSUME ``customer_value``. None of them may
recompute or re-weight it. That prohibition is enforced mechanically by
``tests/structure/checkers.py::find_value_recomputation_violations`` - which
exempts this file alone - because AD-11 exists precisely to stop four
downstream consumers from each reaching for ``Total_Trans_Amt`` and quietly
assigning the same customer four different values.

Changing the value definition
-----------------------------
The definition is not a local decision. Changing it requires editing all three
of the following TOGETHER, in the same change:

  1. this function,
  2. the mart schema documentation that describes the value column,
  3. the CAP-5 limitation wording in the SPEC.

Changing only this function leaves the documented meaning of every downstream
number silently wrong.

Why Total_Trans_Amt, and what that costs
----------------------------------------
Annual transaction amount is the first-order driver of interchange and fee
revenue, and it is the only directly measured spend quantity BankChurners
carries. It is an ASSUMPTION, not a measurement of profit: transaction volume
is not profitability, and this axis deliberately excludes the profiling-only
indicators ``Total_Revolving_Bal`` and ``Credit_Limit`` (SPEC CAP-5 as amended
2026-07-20). See ``docs/implementation-artifacts/value-proxy-report-1-2.md``.

Raw scale is returned deliberately (AD-11): normalising here would make the
mart column uninterpretable. Scaling belongs to the quadrant-assignment step
(story 3-1), which does it internally.

Encoding note: runtime strings stay ASCII (Windows cp949 console).
"""

from __future__ import annotations

import pandas as pd

__all__ = ["customer_value"]

# The measured spend proxy backing the value axis (AD-11, SPEC CAP-5).
#
# PRIVATE ON PURPOSE. Exporting this as a public constant handed callers a
# legitimate import path straight through the AD-11 guard:
#
#     from crm.segment.value import VALUE_COLUMN
#     df[VALUE_COLUMN] * arbitrary_weight   # no literal, no attribute, no violation
#
# That is not a contrived bypass - it is the obvious thing a consumer would
# write, and the guard reported zero violations for it. The leading underscore
# states the intent; the guard now also rejects importing this name (an
# underscore alone stops nobody).
_VALUE_COLUMN = "Total_Trans_Amt"


def customer_value(df: pd.DataFrame) -> pd.Series:
    """Return each customer's value on the RAW measured scale.

    Pure: the input frame is never modified, nothing is written to disk, and no
    global state is touched. The returned Series is a fresh object, so a caller
    mutating it cannot reach back into ``df``.

    Args:
        df: A BankChurners-shaped frame containing ``Total_Trans_Amt``. The
            index is used as-is - rows are neither sorted nor reindexed,
            because consumers join on the caller's index.

    Returns:
        ``Series[float]`` of customer value, indexed exactly like ``df``, on the
        raw scale of the source column (no normalisation, no log transform).

    Raises:
        KeyError: if the required column is absent. The message names the
            column, so a caller can act on it without reading this source.
        ValueError: if the column appears more than once. pandas allows
            duplicate column labels, and ``df[col]`` then returns a DataFrame
            rather than a Series - the return contract would be violated, and
            the failure surfaced as an opaque pandas TypeError several lines
            later instead of naming the real problem here.
    """
    matches = sum(column == _VALUE_COLUMN for column in df.columns)
    if matches == 0:
        raise KeyError(
            f"customer_value requires the column '{_VALUE_COLUMN}' and it is "
            f"absent from the frame passed in."
        )
    if matches > 1:
        raise ValueError(
            f"customer_value requires exactly one '{_VALUE_COLUMN}' column, "
            f"found {matches}. A duplicated label makes the value axis "
            f"ambiguous - deduplicate upstream rather than picking one here."
        )

    # Explicit float cast: the real column is int64, and AC1 fixes the return
    # contract at Series[float]. Relying on the source dtype would make the
    # contract an accident of the input data.
    #
    # Aliasing: under the pandas 3.x Copy-on-Write contract, mutating the
    # returned Series never propagates back into `df`. (Do NOT describe this as
    # "astype always copies" - in pandas 3.x the `copy` argument is ignored and
    # the result may be a lazy CoW view. The guarantee we rely on is the
    # BEHAVIOUR, not an eager memory copy.)
    values = df[_VALUE_COLUMN].astype(float)
    return values.rename(None)
