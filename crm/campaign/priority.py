"""Budget-constrained target priority (CAP-6, FR13, story 3-3).

The 2x2 (story 3-1) says WHO is at risk, `simulate.py` (3-2) says what
contacting one of them is WORTH, and this module answers the question a budget
actually poses: given that you cannot contact everyone, WHO FIRST, and how much
better is that than spraying at random.

Two separate questions, deliberately not merged
-----------------------------------------------
`target_priority()` ranks EVERYONE. `select_within_budget()` decides who gets
bought. Story 3-2 left the choice open - drop the negative-saving customers
before ranking, or rank them last - and this module takes neither option whole:

  - Rank covers all customers, so the mart has no nullable column and story
    4-1 can join without inventing a policy for missing ranks.
  - Selection stops at BOTH limits: the budget, and the sign of the expected
    saving. A contact whose expected saving is negative destroys value at any
    budget, so an unspent budget is not a reason to buy one. Measured on the
    real artifact, buying all 10,127 customers instead of the 8,587 positive
    ones lowers the total from 1,456,900 to 1,454,088.

The consequence a consumer must know: A RANK IS NOT A RECOMMENDATION. Reading
`target_priority` alone and cutting the top N re-introduces exactly the defect
the split avoids, which is why `SELECTED_COLUMN` travels beside it rather than
being left for the reader to derive.

"Dense" rank, and why it cannot be observed here
------------------------------------------------
AD-12 specifies a dense rank with `customer_value` and then `CLIENTNUM` as
tie-breaks. Because `CLIENTNUM` is unique - enforced below - the composite key
has no duplicates, so `dense`, `min` and `first` all collapse to the same
`1..n`. The rank is therefore built as a position in a strict total order, and
this module states the redundancy rather than implying a choice was made. What
the tie-break chain DOES buy is the total order itself: two customers sharing a
rank would let a Tableau view reorder them between refreshes, which is the harm
AD-12 names.

Measured, all 10,127 expected savings are distinct, so the tie-break chain
never fires on the real artifact. It is pinned by synthetic tests only, and the
report says so instead of implying the real run exercised it.

The value axis must be non-negative, and this module checks it
--------------------------------------------------------------
Story 3-2 narrowed its monotonicity claim to non-negative customer value: at a
negative value, a HIGHER churn probability produces a LOWER expected saving
(measured: -35.0 at p=0.1 against -275.0 at p=0.9), so the ranking would invert
for exactly the customers it is meant to prioritise.

The check lives here rather than in `crm/segment/value.py` on purpose.
`customer_value()` returns `Total_Trans_Amt` on its raw scale; "always
non-negative" is a property the current data happens to satisfy (measured
minimum 510.0), not something the definition promises. Promoting it to a
contract would turn a fact about today's data into a guarantee about the
definition, and would also have story 3-3 amending story 1-2's contract. A
consumer that ranks on this output checks its own precondition instead.

What this module deliberately does not know
-------------------------------------------
The savings formula (AD-9: `expected_saving()` is consumed, never re-derived),
the quadrant cuts (AD-12: `quadrant_official` is consumed, never re-cut), and
the assumption sweep (story 3-4). Budget enters ONLY as a contact count,
because `cost_per_contact` is the same for every customer - which makes the
constraint a simple prefix cut rather than a knapsack. That simplicity is a
property of the assumption, not of the code: per-customer costs would make this
a real optimisation problem.

Purity (AD-1/AD-9): inputs are never modified, nothing is written to disk, no
global state. Encoding: runtime strings stay ASCII.
"""

from __future__ import annotations

import dataclasses
import logging
import math

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from crm.config import COST_PER_CONTACT, RANDOM_BASELINE_DRAWS, RANDOM_SEED

__all__ = [
    "BUDGET_BELOW_ONE_CONTACT",
    "BUDGET_BOUND",
    "BOTH_BOUND",
    "BudgetSelection",
    "NO_POSITIVE_CANDIDATES",
    "PRIORITY_COLUMN",
    "POSITIVITY_BOUND",
    "RandomBaseline",
    "SELECTED_COLUMN",
    "ZERO_BUDGET",
    "multiple_over_random",
    "random_baseline",
    "select_within_budget",
    "target_priority",
]

_LOG = logging.getLogger(__name__)

PRIORITY_COLUMN = "target_priority"
SELECTED_COLUMN = "campaign_selected"

# Why the selection stopped. Story AC4 (P1 2-1 lesson): an empty selection is
# not one fact but several, and a caller that cannot tell them apart will
# report "no targets" when the real answer is "no money".
ZERO_BUDGET = "zero_budget"
BUDGET_BELOW_ONE_CONTACT = "budget_below_one_contact"
NO_POSITIVE_CANDIDATES = "no_positive_candidates"
BUDGET_BOUND = "budget"
POSITIVITY_BOUND = "positivity"
BOTH_BOUND = "budget_and_positivity"

_SAVING_AXIS = "expected_saving"
_VALUE_AXIS = "customer_value"
_CLIENTNUM_AXIS = "CLIENTNUM"

# Absolute tolerance for the budget -> contact-count conversion. `budget //
# cost` on floats floors the REPRESENTATION error, not the money: measured,
# `1.0 // 0.1 == 9.0` and `11.0 // 1.1 == 9.0`, each one contact short (story
# 3-3 code review). The shipped COST_GRID is all binary-exact so this is latent
# today, but story 3-4 sweeping a non-dyadic cost (0.1, 1.1, 3.3) makes it live.
# The direction of the error is not predictable (0.1+0.1+0.1 = 0.30000000000004
# rounds the OTHER way), so it can only be guarded, not reasoned about.
_BUDGET_TOL = 1e-9


@dataclasses.dataclass(frozen=True)
class RandomBaseline:
    """What an untargeted campaign of the same size is worth.

    Carries `draws` and `seed` because a mean with neither cannot be audited.
    A SINGLE seeded draw is reproducible but not representative - measured on
    the real artifact with THIS implementation, fifty single draws at 500
    contacts put the multiple anywhere between x8.35 and x13.82 (report section
    3). `spread_total` is reported so the report cannot quote a multiple as if
    it had no width.
    """

    mean_total: float
    spread_total: float
    minimum_total: float
    maximum_total: float
    draws: int
    seed: int
    n_contacts: int


@dataclasses.dataclass(frozen=True)
class BudgetSelection:
    """The ranking, the selection, and the reason the selection ended.

    `priority` covers the WHOLE population and `selected` marks the subset the
    budget actually buys. They travel together for the same reason story 3-1
    returns labels beside thresholds: a consumer that derives one from the
    other re-implements the policy, and a rank alone does not carry the
    positivity cut.
    """

    priority: pd.Series
    selected: pd.Series
    selected_total: float
    selected_count: int
    affordable_contacts: int
    positive_candidates: int
    binding_constraint: str
    budget: float
    cost_per_contact: float


def _require_series(candidate: object, axis_name: str) -> None:
    """Type-check every axis BEFORE anything reads its contents.

    Same reasoning as `simulate.py`: a one-column DataFrame is one `df[["col"]]`
    typo away and would otherwise die inside pandas with a message naming
    neither the argument nor the problem.
    """
    if not isinstance(candidate, pd.Series):
        raise ValueError(
            f"target_priority needs a Series for {axis_name}, got "
            f"{type(candidate).__name__}."
        )


def _validate_axis(series: pd.Series, axis_name: str, *, non_negative: bool) -> np.ndarray:
    """Reject inputs the sort would silently accept.

    A NaN does not raise when sorted - pandas parks it at the end regardless of
    `ascending`, so a missing saving would quietly become the lowest priority
    instead of an error. That is the failure mode this catches: a customer
    dropped from the campaign because an upstream join lost their row.
    """
    if series.empty:
        raise ValueError(
            f"target_priority received an empty {axis_name} axis. An empty "
            f"population would produce an empty ranking and a multiple of 1.0, "
            f"both of which read as findings rather than as a missing input."
        )
    if is_bool_dtype(series) or not is_numeric_dtype(series):
        raise ValueError(
            f"target_priority needs a numeric {axis_name} axis, got dtype "
            f"'{series.dtype}'. Anything sortable would otherwise produce a "
            f"plausible-looking ranking."
        )
    if series.isna().any():
        count = int(series.isna().sum())
        raise ValueError(
            f"target_priority received {count} missing entries on the "
            f"{axis_name} axis. Sorting parks NaN at the end whatever the "
            f"direction, so those customers would silently become the lowest "
            f"priority instead of being reported."
        )
    values = series.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(
            f"target_priority received non-finite entries on the {axis_name} "
            f"axis. An infinity sorts to one end and would take the top or "
            f"bottom of the campaign list with it."
        )
    if non_negative and (values < 0.0).any():
        count = int((values < 0.0).sum())
        raise ValueError(
            f"target_priority received {count} negative {axis_name} entries, "
            f"and this ranking requires them to be non-negative. Expected "
            f"saving is monotonic in churn probability only where value is "
            f"non-negative: at a negative value the relationship REVERSES "
            f"(measured, -35.0 at p=0.1 against -275.0 at p=0.9), so the "
            f"riskiest customers would sort to the BOTTOM of the campaign "
            f"list. Fix the value definition upstream rather than clipping "
            f"here - AD-11 makes `customer_value()` the only place that "
            f"decides what this axis means."
        )
    return values


def _validate_alignment(
    expected_saving: pd.Series, value: pd.Series, clientnum: pd.Series
) -> None:
    """Check the PAIRING, and then check the labels against the index.

    Length first, for the reason story 3-0 and 3-2 both had to fix: validating
    contents first reports "missing entries" while the fact that the two
    populations differ in SIZE never reaches the screen.

    The last check is the one this module can make and its neighbours cannot.
    `churn_scored.parquet` is not in the same row order as
    `bankchurners.parquet`, yet both carry a plain `RangeIndex`, so
    `Index.equals` returns True and every guard in `simulate.py` passes -
    measured, that misalignment inflated the total by 37% with nothing raised.
    Because `CLIENTNUM` arrives here as a sort key, its VALUES can be compared
    against the index labels. The guard is partial by design and says so: it
    only fires when the index is itself CLIENTNUM-shaped, which is how the mart
    (story 4-1) will carry it.
    """
    if len(expected_saving) != len(value) or len(expected_saving) != len(clientnum):
        raise ValueError(
            f"target_priority needs one value and one CLIENTNUM per expected "
            f"saving: got {len(expected_saving)}, {len(value)} and "
            f"{len(clientnum)}. Differing lengths mean these came from "
            f"different populations, not that one of them is short."
        )
    for other, axis_name in ((value, _VALUE_AXIS), (clientnum, _CLIENTNUM_AXIS)):
        if not expected_saving.index.equals(other.index):
            raise ValueError(
                f"target_priority needs {_SAVING_AXIS} and {axis_name} to share "
                f"an index. pandas would ALIGN mismatched labels and fill the "
                f"gaps with NaN, so a join done wrong upstream would surface as "
                f"a plausible ranking of the wrong customers."
            )
        if expected_saving.index.dtype != other.index.dtype:
            raise ValueError(
                f"target_priority needs {_SAVING_AXIS} and {axis_name} to share "
                f"an index dtype, got {expected_saving.index.dtype} and "
                f"{other.index.dtype}. `Index.equals` ignores dtype, so these "
                f"compare equal here and then fail to match in the mart."
            )
    if not expected_saving.index.is_unique:
        duplicated = expected_saving.index[expected_saving.index.duplicated()]
        raise ValueError(
            f"target_priority received a duplicated customer index "
            f"{duplicated.unique()[:5].tolist()}. A fan-out join would give one "
            f"customer several ranks and spend the budget on them twice."
        )
    if not clientnum.is_unique:
        duplicated = clientnum[clientnum.duplicated()]
        raise ValueError(
            f"target_priority received duplicated CLIENTNUM values "
            f"{duplicated.unique()[:5].tolist()}. CLIENTNUM is the final "
            f"tie-break, so duplicates would leave the order undetermined for "
            f"exactly the customers the earlier keys could not separate."
        )
    if expected_saving.index.name == _CLIENTNUM_AXIS and not np.array_equal(
        expected_saving.index.to_numpy(), clientnum.to_numpy()
    ):
        raise ValueError(
            "target_priority got a CLIENTNUM column that disagrees with the "
            "CLIENTNUM index. That is the signature of two frames combined by "
            "ROW POSITION rather than by label: `churn_scored.parquet` and "
            "`bankchurners.parquet` are in different row orders but both carry "
            "a plain RangeIndex, so `Index.equals` cannot see it (measured: "
            "the total came out 37% high with nothing raised). Join on "
            "CLIENTNUM."
        )


def target_priority(
    expected_saving: pd.Series,
    value: pd.Series,
    clientnum: pd.Series,
) -> pd.Series:
    """Rank every customer for contact, best first (FR13, AD-12).

    Args:
        expected_saving: Per-customer expected saving, the `expected_saving()`
            output from story 3-2 (AD-9 - consumed, never re-derived). Negative
            entries are ranked, not dropped; the sign is a SELECTION concern,
            not a ranking one.
        value: Customer value per customer, the persisted `customer_value`
            output on its raw scale (AD-11 - consumed, never recomputed or
            re-weighted). Used ONLY as a tie-break key. Must be non-negative;
            see the module docstring for why that is checked here.
        clientnum: Customer identifier, the final tie-break. Must be unique,
            and must agree with the index when the index is itself CLIENTNUM.

    Returns:
        ``Series[int64]`` named :data:`PRIORITY_COLUMN`, indexed exactly like
        the inputs, taking every value in ``1..n`` exactly once. 1 is contacted
        first.

    Raises:
        ValueError: on a non-Series input, an empty axis, a non-numeric axis,
            missing or non-finite entries, a negative customer value,
            mismatched lengths, indexes or index dtypes, a duplicated customer
            index, duplicated CLIENTNUM values, or a CLIENTNUM column that
            disagrees with a CLIENTNUM index.
    """
    _require_series(expected_saving, _SAVING_AXIS)
    _require_series(value, _VALUE_AXIS)
    _require_series(clientnum, _CLIENTNUM_AXIS)
    _validate_alignment(expected_saving, value, clientnum)
    _validate_axis(expected_saving, _SAVING_AXIS, non_negative=False)
    _validate_axis(value, _VALUE_AXIS, non_negative=True)
    _validate_axis(clientnum, _CLIENTNUM_AXIS, non_negative=False)

    # `np.lexsort` orders by the LAST key first, so the keys are listed in
    # reverse priority. Negating the two descending keys keeps a single stable
    # sort rather than three chained ones, whose relative order would then
    # depend on the sort being stable rather than on the keys being complete.
    order = np.lexsort(
        (
            clientnum.to_numpy(),
            -value.to_numpy(dtype=float),
            -expected_saving.to_numpy(dtype=float),
        )
    )

    # Position in the strict total order. Equivalent to a dense rank here
    # because CLIENTNUM is unique and validated so - see the module docstring
    # rather than reading a choice into this line.
    ranks = np.empty(len(order), dtype=np.int64)
    ranks[order] = np.arange(1, len(order) + 1, dtype=np.int64)

    return pd.Series(ranks, index=expected_saving.index, name=PRIORITY_COLUMN)


def _validate_budget(budget: float, cost_per_contact: float) -> None:
    """Guard the two numbers that turn a ranking into a campaign."""
    if not math.isfinite(budget):
        raise ValueError(
            f"budget must be finite, got {budget}. An infinite budget would "
            f"make the positivity cut the only limit and hide the fact that no "
            f"budget was actually supplied."
        )
    if budget < 0.0:
        raise ValueError(
            f"budget must be non-negative, got {budget}. A negative budget is "
            f"not an empty campaign, it is a mistake in the caller."
        )
    if not math.isfinite(cost_per_contact):
        raise ValueError(f"cost_per_contact must be finite, got {cost_per_contact}.")
    # Strictly positive, unlike `expected_saving`, which allows a zero cost
    # because a free contact is arithmetically harmless there. Here a zero cost
    # makes the budget buy an unbounded number of contacts, so "top N within
    # budget" would silently stop being a budget constraint at all.
    if cost_per_contact <= 0.0:
        raise ValueError(
            f"cost_per_contact must be positive, got {cost_per_contact}. At "
            f"zero the budget buys everyone and the constraint this function "
            f"exists to apply disappears without any error."
        )
    # Both operands are finite here, but their QUOTIENT can still overflow: a
    # huge budget over a tiny cost (1.0 / 5e-324) is +inf, and `int(inf)` raises
    # a bare OverflowError several lines later - a failure mode outside this
    # module's documented `ValueError` contract (story 3-3 code review).
    if not math.isfinite(budget / cost_per_contact):
        raise ValueError(
            f"budget / cost_per_contact is not finite (budget={budget}, "
            f"cost_per_contact={cost_per_contact}). The contact count would "
            f"overflow; the cost is too small relative to the budget to be a "
            f"real per-contact price."
        )


def select_within_budget(
    expected_saving: pd.Series,
    value: pd.Series,
    clientnum: pd.Series,
    *,
    budget: float,
    cost_per_contact: float = COST_PER_CONTACT,
) -> BudgetSelection:
    """Buy down the priority list until the money OR the value runs out (FR13).

    The second limit is the one worth restating: selection stops at the last
    customer whose expected saving is positive, even when budget remains.
    Contacting a negative-saving customer lowers the campaign total, so an
    unspent budget is a better outcome than a spent one.

    Budget is converted to a contact COUNT rather than being spent per
    customer, because `cost_per_contact` is the same for everyone - the ASSUMED
    "one contact per customer, one price" model story 3-2 records. That makes
    the constraint a prefix cut instead of a knapsack; per-customer costs would
    not.

    Args:
        expected_saving: Per-customer expected saving (story 3-2 output).
        value: Customer value, tie-break key only (AD-11).
        clientnum: Customer identifier, final tie-break.
        budget: Total ASSUMED spend available, unitless (NFR3 - the data
            carries no currency, so attaching one would fabricate information).
        cost_per_contact: ASSUMED cost of one contact. Defaults to the single
            config constant.

    Returns:
        A :class:`BudgetSelection` carrying the full ranking, the selected
        subset, and `binding_constraint` naming WHY the selection ended.

    Raises:
        ValueError: for the reasons :func:`target_priority` raises, plus a
            non-finite or negative budget, a non-positive ``cost_per_contact``,
            or a ``budget / cost_per_contact`` that overflows to non-finite.
    """
    _validate_budget(budget, cost_per_contact)
    priority = target_priority(expected_saving, value, clientnum)

    affordable_contacts = int(math.floor(budget / cost_per_contact + _BUDGET_TOL))
    is_positive = expected_saving > 0.0
    positive_candidates = int(is_positive.sum())
    selected_count = min(affordable_contacts, positive_candidates)

    # Both limits are applied, so a rank inside the budget that is NOT positive
    # is left unselected rather than bought with the leftover money.
    #
    # The mask is REDUNDANT as written and kept deliberately. Because the
    # primary sort key is the saving itself, the top `positive_candidates`
    # ranks are exactly the positive customers, so the `min()` above already
    # excludes every negative one - mutation run M5 (story 3-3) removed this
    # mask and no test could tell, which is the definition of an equivalent
    # mutant rather than a gap in the suite. What it defends against is a wrong
    # `selected_count`: on the fixture savings [10, 5, -2] with an unbounded
    # budget, dropping the `min()` but KEEPING this mask still selects only the
    # positives (total 15.0), while dropping both buys the -2 contact (total
    # 13.0). Those figures come from a mutation run, not a committed test, so
    # they are reproducible only by re-planting the mutation on that fixture.
    # `.astype(bool)` pins the dtype: a nullable Int64/Float64 saving axis (the
    # mart-friendly dtypes story 4-1 may hand in) makes `& is_positive` return a
    # `BooleanDtype` mask, so `campaign_selected` would land in parquet as
    # `boolean` for one caller and `bool` for another (story 3-3 code review).
    selected = ((priority <= selected_count) & is_positive).astype(bool)
    selected.name = SELECTED_COLUMN

    # Order matters (story 3-3 code review): when NO contact is affordable, the
    # budget is the total blocker and is reported first - and a budget of
    # exactly zero is a different fact from a budget that merely falls short of
    # one contact's price (4.99 against a cost of 5.0). Only once at least one
    # contact is affordable does the positivity of the candidates decide the
    # outcome. The earlier `positive_candidates == 0` first meant an all-negative
    # population with a zero budget reported "no candidates" and hid the fact
    # that there was also no money - the exact confusion AC4 exists to prevent.
    if affordable_contacts == 0:
        binding_constraint = ZERO_BUDGET if budget == 0.0 else BUDGET_BELOW_ONE_CONTACT
    elif positive_candidates == 0:
        binding_constraint = NO_POSITIVE_CANDIDATES
    elif affordable_contacts < positive_candidates:
        binding_constraint = BUDGET_BOUND
    elif affordable_contacts > positive_candidates:
        binding_constraint = POSITIVITY_BOUND
    else:
        binding_constraint = BOTH_BOUND

    selected_total = float(expected_saving[selected].sum())

    # Recorded, not returned silently (AC4, P1 2-1): an empty selection that
    # only shows up as an empty frame is indistinguishable from a population
    # with no customers in it.
    _LOG.info(
        "select_within_budget: selected %d of %d customers (%d positive, "
        "budget buys %d contacts), limited by %s",
        selected_count,
        len(priority),
        positive_candidates,
        affordable_contacts,
        binding_constraint,
    )

    return BudgetSelection(
        priority=priority,
        selected=selected,
        selected_total=selected_total,
        selected_count=selected_count,
        affordable_contacts=affordable_contacts,
        positive_candidates=positive_candidates,
        binding_constraint=binding_constraint,
        budget=float(budget),
        cost_per_contact=float(cost_per_contact),
    )


def random_baseline(
    expected_saving: pd.Series,
    *,
    n_contacts: int,
    draws: int = RANDOM_BASELINE_DRAWS,
    seed: int = RANDOM_SEED,
) -> RandomBaseline:
    """What contacting `n_contacts` customers AT RANDOM is worth (AD-7).

    Repeated draws, not one. A single seeded draw is reproducible, which is
    what AD-7 asks for, but reproducibility is not representativeness:
    measured on the real artifact with this implementation at 500 contacts,
    changing only the seed moves the resulting multiple between x8.35 and
    x13.82 (report section 3). Quoting one of those to two decimal places would
    present a spread as a fact.

    Args:
        expected_saving: Per-customer expected saving for the WHOLE population,
            which is the pool a random campaign would draw from.
        n_contacts: How many customers the random campaign contacts. Compare
            like with like - pass the count the targeted campaign bought.
        draws: How many independent random campaigns to average. Exposed so the
            report can state it; a mean with no draw count cannot be audited.
        seed: Fixed for reproducibility (AD-7).

    Returns:
        A :class:`RandomBaseline` carrying the mean, its spread, and the
        provenance needed to reproduce it.

    Raises:
        ValueError: on a non-int (or ``bool``) ``n_contacts``/``draws``/``seed``,
            a non-positive ``draws``, a negative ``seed``, or an ``n_contacts``
            outside ``0..len(expected_saving)``.
    """
    _require_series(expected_saving, _SAVING_AXIS)
    _validate_axis(expected_saving, _SAVING_AXIS, non_negative=False)
    # Type-check before the range checks: `0 <= 2.5 <= n` and `3.7 > 0` both
    # pass, and the failure then surfaces from numpy naming neither the argument
    # nor this function (story 3-3 code review). `bool` is the sharp edge - it
    # is an `int` subtype, so a flag passed by mistake would clear the range
    # test. Rejected here with the same discipline `_require_series` applies.
    for _name, _val in (("n_contacts", n_contacts), ("draws", draws), ("seed", seed)):
        if isinstance(_val, bool) or not isinstance(_val, (int, np.integer)):
            raise ValueError(
                f"{_name} must be an int, got {type(_val).__name__} ({_val!r})."
            )
    if draws <= 0:
        raise ValueError(
            f"draws must be positive, got {draws}. The point of this function "
            f"is that one draw is not a baseline."
        )
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}.")
    if not 0 <= n_contacts <= len(expected_saving):
        raise ValueError(
            f"n_contacts must lie in 0..{len(expected_saving)}, got "
            f"{n_contacts}. Sampling more customers than exist would have to "
            f"draw someone twice and would overstate the baseline."
        )

    population = expected_saving.to_numpy(dtype=float)

    # Sampling the WHOLE population without replacement is a permutation, so
    # every draw sums to the same number and the spread is a STRUCTURAL zero,
    # not a measured one (story 3-3 code review). Short-circuit rather than burn
    # `draws` identical permutations and report a zero width that a reader could
    # mistake for a tight estimate. `n_contacts == 0` is the same: the empty sum
    # is 0.0 with no variation.
    if n_contacts == len(population) or n_contacts == 0:
        total = float(population.sum()) if n_contacts else 0.0
        return RandomBaseline(
            mean_total=total,
            spread_total=0.0,
            minimum_total=total,
            maximum_total=total,
            draws=draws,
            seed=seed,
            n_contacts=n_contacts,
        )

    rng = np.random.default_rng(seed)
    totals = np.fromiter(
        (
            rng.choice(population, size=n_contacts, replace=False).sum()
            for _ in range(draws)
        ),
        dtype=float,
        count=draws,
    )

    return RandomBaseline(
        mean_total=float(totals.mean()),
        spread_total=float(totals.std()),
        minimum_total=float(totals.min()),
        maximum_total=float(totals.max()),
        draws=draws,
        seed=seed,
        n_contacts=n_contacts,
    )


def multiple_over_random(selection: BudgetSelection, baseline: RandomBaseline) -> float:
    """How many times better the targeted campaign is (FR13, success signal 2).

    Takes the two RESULT OBJECTS, not a bare float (story 3-3 code review,
    decision by party). The earlier signature accepted any ``selected_total``,
    so an 8,587-contact selection could be divided by a 100-contact baseline
    and print x99 with nothing raised - a plausible, publishable, wrong
    headline. With the objects in hand the function reads the numerator off
    ``selection.selected_total`` itself and REFUSES a baseline drawn at a
    different contact count, so the mismatch is no longer expressible at the
    call site. The numerator needs no separate finiteness guard for the same
    reason: ``BudgetSelection`` is built from validated axes and a selection
    restricted to strictly positive savings, so its total is finite and
    non-negative by construction.

    Refuses a non-positive denominator instead of returning a ratio: with a
    zero or negative random total, the arithmetic yields a number that reads
    as a performance ratio and is not one.

    THE RESULT IS A FUNCTION OF THE BUDGET and must never be quoted without
    it. Measured with the D1 policy, the multiple falls monotonically from
    x17.27 at 100 contacts to x1.18 at the positive-only floor (8,587
    contacts): once the budget covers every positive customer, buying more
    would only add negative-saving contacts, which the selection refuses. It
    does NOT reach x1.00 - that belongs to the rejected budget-only policy,
    which keeps buying to the full population (report section 2). The headline
    is the curve, not any single point on it.

    Raises:
        ValueError: on a non-``BudgetSelection``/``RandomBaseline`` argument,
            a baseline drawn at a different contact count than the selection
            bought, or a ``baseline.mean_total`` that is not strictly
            positive.
    """
    if not isinstance(selection, BudgetSelection):
        raise ValueError(
            f"multiple_over_random needs a BudgetSelection, got "
            f"{type(selection).__name__}. Passing a bare total is exactly the "
            f"call shape that allowed a mismatched baseline (story 3-3 code "
            f"review)."
        )
    if not isinstance(baseline, RandomBaseline):
        raise ValueError(
            f"multiple_over_random needs a RandomBaseline, got "
            f"{type(baseline).__name__}."
        )
    if baseline.n_contacts != selection.selected_count:
        raise ValueError(
            f"the baseline was drawn at {baseline.n_contacts} contacts but the "
            f"selection bought {selection.selected_count}. Comparing totals of "
            f"different campaign sizes produces a plausible-looking multiple "
            f"that answers no question - measured, an 8,587-contact selection "
            f"over a 100-contact baseline printed x99 with nothing raised. "
            f"Re-draw the baseline with n_contacts={selection.selected_count}."
        )
    if not baseline.mean_total > 0.0:
        raise ValueError(
            f"a multiple needs a positive baseline, got "
            f"{baseline.mean_total}. Dividing by a zero or negative random "
            f"total produces a number that reads as a performance ratio and is "
            f"not one; report the two totals separately instead."
        )
    return selection.selected_total / baseline.mean_total
