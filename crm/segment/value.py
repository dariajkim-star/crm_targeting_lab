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

# The measured spend proxy backing the value axis (AD-11, SPEC CAP-5).
VALUE_COLUMN = "Total_Trans_Amt"


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
    """
    if VALUE_COLUMN not in df.columns:
        raise KeyError(
            f"customer_value requires the column '{VALUE_COLUMN}' and it is "
            f"absent from the frame passed in."
        )

    # Explicit float cast: the real column is int64, and AC1 fixes the return
    # contract at Series[float]. Relying on the source dtype would make the
    # contract an accident of the input data.
    # `.astype` returns a copy even when the dtype already matches (copy=True
    # is the default), which is what keeps the result from aliasing `df`.
    values = df[VALUE_COLUMN].astype(float)
    return values.rename(None)
