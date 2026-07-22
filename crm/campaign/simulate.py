"""Expected saving per customer (CAP-6, FR12, story 3-2).

This is where the project first answers "HOW MUCH" - the 2x2 (story 3-1) says
WHO, and this says what contacting one of them is worth:

    expected_saving = P(churn) * customer_value * retention_rate - cost

Read one term at a time: `P(churn) * customer_value` is the value at risk;
multiplying by `retention_rate` is the share of it a campaign is assumed to
recover; subtracting `cost` charges the contact whether or not it works.

Two of those four are ASSUMPTIONS, not measurements
---------------------------------------------------
`retention_rate` and `cost_per_contact` come from `crm/config.py` labelled
`# source: 정책가정`, and every artifact built on this function has to label
them the same way (NFR1). The break-even point sits at

    P(churn) * customer_value = cost_per_contact / retention_rate

which on the shipped defaults is 16.67 - and since the median customer value is
3,899, a probability above 0.0043 clears it. That is why "most customers show a
positive expected saving" is a statement about `cost = 5.0`, not a finding
about the customer base. Story 3-4 (CAP-7) is what turns the assumption into a
range; this module only makes the number the sweep moves.

Which probability column (story 3-0)
------------------------------------
`churn_prob_calibrated`, never `churn_score`. Both are in `[0, 1]` and sit in
the same frame, so nothing in the type system distinguishes them - but only the
calibrated one is a probability. Measured on the real artifact, the raw
out-of-fold score has mean 0.1946 against an observed attrition rate of 0.1607,
and using it here inflates the total expected saving by +19.0%. The 2x2 uses the
raw score on purpose (it needs only the ORDER); money needs the magnitude to
mean what it says.

What this module deliberately does not know
-------------------------------------------
Budget, ranking, quadrants, sensitivity grids. It answers for ONE customer at a
time and has no opinion about who to contact: `target_priority` and the budget
cut are story 3-3 (AD-12), the assumption sweep is 3-4, and AD-9 fixes the
direction `matrix -> simulate -> sensitivity` with a structure guard. Story 3-4
re-calls this function with different arguments rather than re-deriving the
formula - that is why the assumptions are parameters and not module constants.

Customer value is CONSUMED, never recomputed or re-weighted (AD-11). The caller
passes the persisted `crm.segment.value.customer_value` output on its RAW
scale. The mismatch between a cost of 5.0 and a value of 3,899 is not a problem
to normalise away - the data carries no currency unit (NFR3) and rescaling
either side would make the output stop being money.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crm.config import COST_PER_CONTACT, RETENTION_SUCCESS_RATE

__all__ = ["SAVING_COLUMN", "expected_saving"]

SAVING_COLUMN = "expected_saving"

_PROB_AXIS = "churn_prob_calibrated"
_VALUE_AXIS = "customer value"


def _validate_axis(series: pd.Series, axis_name: str) -> np.ndarray:
    """Reject inputs the arithmetic would silently accept.

    Unlike the quantile cuts in `matrix.py`, multiplication does not skip NaN -
    it propagates. That is better, but only if the failure is named here rather
    than surfacing three stages later as a mart cell that is empty for reasons
    nobody can reconstruct. An infinity is worse: it survives the arithmetic and
    a single customer can then dominate any total the report prints.
    """
    if series.empty:
        raise ValueError(
            f"expected_saving received an empty {axis_name} axis. An empty "
            f"population would sum to a confident zero."
        )
    if series.isna().any():
        count = int(series.isna().sum())
        raise ValueError(
            f"expected_saving received {count} missing {axis_name} value(s). "
            f"The product would be NaN for those customers and any total would "
            f"quietly drop them - fix the upstream join rather than imputing."
        )
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            f"expected_saving received non-finite {axis_name} value(s). One "
            f"infinity survives every step below and would dominate the total."
        )
    if axis_name == _PROB_AXIS and ((values < 0.0) | (values > 1.0)).any():
        out_of_range = int(((values < 0.0) | (values > 1.0)).sum())
        raise ValueError(
            f"expected_saving received {out_of_range} probability value(s) "
            f"outside [0, 1]. This argument is `churn_prob_calibrated`; a raw "
            f"score on another scale - or the value axis passed by mistake - "
            f"would still produce plausible-looking money."
        )
    # No range check on the value axis: `customer_value()` returns the raw
    # measured scale and promises nothing about sign (AD-11 - the value
    # definition is not this module's to extend). Same reasoning as matrix.py.
    return values


def _validate_pair(churn_prob_calibrated: pd.Series, value: pd.Series) -> None:
    if len(churn_prob_calibrated) != len(value):
        raise ValueError(
            f"expected_saving needs one probability per customer value: got "
            f"{len(churn_prob_calibrated)} and {len(value)}."
        )
    if not churn_prob_calibrated.index.equals(value.index):
        raise ValueError(
            "expected_saving needs the two inputs to share an index. pandas "
            "would ALIGN mismatched labels and fill the gaps with NaN, so a "
            "join done wrong upstream would surface as plausible money for the "
            "wrong customers."
        )
    if not churn_prob_calibrated.index.is_unique:
        duplicated = churn_prob_calibrated.index[churn_prob_calibrated.index.duplicated()]
        raise ValueError(
            f"expected_saving received a duplicated customer index "
            f"{duplicated.unique()[:5].tolist()}. A fan-out join would count "
            f"the same customer's saving more than once in every total."
        )


def _validate_assumptions(retention_rate: float, cost_per_contact: float) -> None:
    """Guard the two parameters that are assumptions rather than data.

    Checked here and not only in `crm/config.py` because story 3-4 sweeps them
    at the call site: the import-time guard sees the config defaults and cannot
    see a grid point built by a caller.
    """
    if not 0.0 <= retention_rate <= 1.0:
        raise ValueError(
            f"retention_rate must lie in [0, 1], got {retention_rate}. Above 1 "
            f"the campaign would save more customers than are at risk, and the "
            f"expected saving would exceed the value it is derived from."
        )
    if cost_per_contact < 0.0:
        raise ValueError(
            f"cost_per_contact must be non-negative, got {cost_per_contact}. A "
            f"negative cost is a subsidy, and it would make every customer look "
            f"worth contacting regardless of their risk."
        )


def expected_saving(
    churn_prob_calibrated: pd.Series,
    value: pd.Series,
    *,
    retention_rate: float = RETENTION_SUCCESS_RATE,
    cost_per_contact: float = COST_PER_CONTACT,
) -> pd.Series:
    """Expected saving from contacting each customer once (FR12).

    Args:
        churn_prob_calibrated: The CALIBRATED churn probability per customer,
            in ``[0, 1]``. This is the `churn_prob_calibrated` column, not
            `churn_score` - the latter is the raw out-of-fold ranking signal
            (story 3-0) and using it here inflates the total by +19.0%
            (measured). Both columns are `[0, 1]` floats, so this argument name
            and this sentence are the only things standing between them.
        value: Customer value per customer, the persisted ``customer_value``
            output on its raw scale (AD-11 - consumed, never recomputed or
            re-weighted).
        retention_rate: ASSUMED share of contacted at-risk customers who stay.
            Defaults to the single config constant; story 3-4 passes grid
            points instead of editing the constant.
        cost_per_contact: ASSUMED cost of one contact, unitless (NFR3 - the
            data carries no currency, so attaching one would fabricate
            information). Charged whether or not the contact works.

    Returns:
        ``Series[float]`` named :data:`SAVING_COLUMN`, indexed exactly like the
        inputs. Negative where the value at risk does not cover the contact -
        that is a real answer ("do not contact"), not a failure.

    Raises:
        ValueError: on an empty axis, missing or non-finite values, a
            probability outside ``[0, 1]``, mismatched lengths or indexes, a
            duplicated customer index, a ``retention_rate`` outside ``[0, 1]``,
            or a negative ``cost_per_contact``.
    """
    _validate_assumptions(retention_rate, cost_per_contact)
    probabilities = _validate_axis(churn_prob_calibrated, _PROB_AXIS)
    values = _validate_axis(value, _VALUE_AXIS)
    _validate_pair(churn_prob_calibrated, value)

    # Written as (value at risk) * rate - cost so the terms line up with the
    # sentence in the module docstring; grouping it any other way computes the
    # same number and reads like something else.
    value_at_risk = probabilities * values
    saving = value_at_risk * retention_rate - cost_per_contact

    return pd.Series(saving, index=churn_prob_calibrated.index, name=SAVING_COLUMN)
