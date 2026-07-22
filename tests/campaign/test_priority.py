"""Behavioural tests for budget-constrained targeting (story 3-3, CAP-6/FR13).

Why these assertions and not others
-----------------------------------
Re-sorting by the same three keys inside the test and comparing would prove only
that the same sort was typed twice. Each test below names a PROPERTY the
decision frame depends on:

  - TOTAL ORDER (AC1). The rank must be a bijection onto ``1..n``: no ties, no
    gaps. The stated harm is a Tableau view whose sort order shuffles between
    refreshes, and that happens exactly when two customers share a rank.
  - THE TIE CHAIN IS UNTESTABLE ON REAL DATA (story 3-3 trap 2). Measured, all
    10,127 expected savings are distinct, so neither `customer_value` nor
    `CLIENTNUM` ever breaks a tie in production. Every tie test here is
    therefore a SYNTHETIC fixture, and that is a statement about coverage, not
    a shortcut.
  - "DENSE" IS INERT HERE, and this file says so rather than claiming a mutant
    it cannot kill. Once `CLIENTNUM` is unique - which `target_priority`
    enforces - the composite key admits no duplicates, so `dense`, `min` and
    `first` all produce the same `1..n`. The mutation story 3-3 listed
    (`dense -> min/first`) has nothing to kill, exactly like the swap mutant
    story 3-2 struck from its own list. What IS killable is the ORDER of the
    tie-break keys and their direction, and those mutants are exercised below.
  - THE NEGATIVE CUT (AC5/D1). Budget exhaustion is not the only stopping
    condition: a contact whose expected saving is negative destroys value at
    any budget. Measured, buying all 10,127 instead of the 8,587 positives
    costs 2,812. The two conditions are pinned separately so a future edit
    cannot drop one and stay green.
  - NON-NEGATIVE VALUE (AC6/D2). Story 3-2 narrowed its monotonicity claim to
    non-negative value and handed the check here. `value.py` is deliberately
    NOT changed - the guard lives at the consumer boundary.
  - VALUE PASS-THROUGH (AC7). AD-11 says `customer_value()` alone defines
    value. Story 3-2 pinned this with a sentinel EQUALITY test; that method is
    useless here, because a MONOTONE transform of the tie-break key leaves
    every rank identical. The contract is therefore pinned by tie-group
    ORDERING and the mutants are NON-monotone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from crm.campaign.priority import (
    NO_POSITIVE_CANDIDATES,
    PRIORITY_COLUMN,
    SELECTED_COLUMN,
    ZERO_BUDGET,
    multiple_over_random,
    random_baseline,
    select_within_budget,
    target_priority,
)
from crm.config import COST_PER_CONTACT, RANDOM_SEED


def _population(savings, values, clientnums):
    """Three aligned axes indexed by CLIENTNUM, the shape the mart will use."""
    index = pd.Index(clientnums, name="CLIENTNUM")
    return (
        pd.Series(savings, index=index, dtype=float, name="expected_saving"),
        pd.Series(values, index=index, dtype=float, name="customer_value"),
        pd.Series(clientnums, index=index, dtype="int64", name="CLIENTNUM"),
    )


@pytest.fixture
def distinct():
    """No ties anywhere - the shape real data actually has (trap 2)."""
    return _population([10.0, 30.0, -2.0, 20.0], [100.0, 300.0, 50.0, 200.0], [4, 1, 3, 2])


@pytest.fixture
def tied_on_saving():
    """Two customers share a saving; `customer_value` must break it."""
    return _population([5.0, 5.0, 9.0], [100.0, 900.0, 50.0], [11, 22, 33])


@pytest.fixture
def tied_on_saving_and_value():
    """Two customers share saving AND value; only CLIENTNUM is left."""
    return _population([5.0, 5.0, 9.0], [100.0, 100.0, 50.0], [77, 22, 33])


# --- The hard-coded oracle ---------------------------------------------------


def test_one_hand_computed_ranking(distinct):
    """The single anchor. Every other ranking test is a property.

    savings 10/30/-2/20 for CLIENTNUM 4/1/3/2. Sorted descending by saving:
      30 (id 1) -> 1
      20 (id 2) -> 2
      10 (id 4) -> 3
      -2 (id 3) -> 4
    """
    saving, value, clientnum = distinct

    ranks = target_priority(saving, value, clientnum)

    assert ranks.loc[1] == 1
    assert ranks.loc[2] == 2
    assert ranks.loc[4] == 3
    assert ranks.loc[3] == 4


# --- Total order (AC1) -------------------------------------------------------


def test_the_rank_is_a_bijection_onto_one_through_n(distinct):
    """No ties and no gaps - the property a stable Tableau sort needs."""
    saving, value, clientnum = distinct

    ranks = target_priority(saving, value, clientnum)

    assert sorted(ranks.tolist()) == [1, 2, 3, 4]


def test_negative_savings_are_ranked_not_dropped(distinct):
    """D1: everyone gets a rank; the negative cut belongs to SELECTION."""
    saving, value, clientnum = distinct

    ranks = target_priority(saving, value, clientnum)

    assert len(ranks) == len(saving)
    assert ranks.notna().all()


def test_the_output_is_named_and_indexed_like_the_input(distinct):
    saving, value, clientnum = distinct

    ranks = target_priority(saving, value, clientnum)

    assert ranks.name == PRIORITY_COLUMN
    assert ranks.index.equals(saving.index)


def test_shuffling_the_input_rows_does_not_change_anyone_s_rank(distinct):
    """AC1's second clause: re-running must not reorder the mart.

    This is the test that would catch a rank derived from row POSITION rather
    than from the keys.
    """
    saving, value, clientnum = distinct
    shuffled = [2, 0, 3, 1]

    original = target_priority(saving, value, clientnum)
    reordered = target_priority(
        saving.iloc[shuffled], value.iloc[shuffled], clientnum.iloc[shuffled]
    )

    pd.testing.assert_series_equal(
        original.sort_index(), reordered.sort_index(), check_like=True
    )


def test_rerunning_on_identical_input_is_identical(distinct):
    saving, value, clientnum = distinct

    first = target_priority(saving, value, clientnum)
    second = target_priority(saving, value, clientnum)

    pd.testing.assert_series_equal(first, second)


# --- The tie chain, which only synthetic data can reach (trap 2) -------------


def test_a_saving_tie_is_broken_by_higher_customer_value(tied_on_saving):
    saving, value, clientnum = tied_on_saving

    ranks = target_priority(saving, value, clientnum)

    # 9.0 wins outright; between the two 5.0s the value 900 outranks 100.
    assert ranks.loc[33] == 1
    assert ranks.loc[22] == 2
    assert ranks.loc[11] == 3


def test_a_saving_and_value_tie_is_broken_by_lower_clientnum(
    tied_on_saving_and_value,
):
    saving, value, clientnum = tied_on_saving_and_value

    ranks = target_priority(saving, value, clientnum)

    assert ranks.loc[33] == 1
    assert ranks.loc[22] == 2
    assert ranks.loc[77] == 3


def test_the_tie_break_keys_are_applied_in_the_specified_priority():
    """Value must outrank CLIENTNUM, not the other way round.

    Built so the two orderings disagree: the higher-value customer also has the
    higher CLIENTNUM, so a swapped key order flips these two ranks.
    """
    saving, value, clientnum = _population([5.0, 5.0], [100.0, 900.0], [1, 2])

    ranks = target_priority(saving, value, clientnum)

    assert ranks.loc[2] == 1
    assert ranks.loc[1] == 2


# --- AC7: the value axis is a sort key, used as given ------------------------


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(lambda v: v.max() - v, id="order_reversed"),
        pytest.param(lambda v: (v - v.median()).abs(), id="folded_about_median"),
    ],
)
def test_a_non_monotone_transform_of_the_value_key_changes_the_ranking(transform):
    """AC7, and the reason story 3-2's sentinel method does NOT transfer.

    A monotone re-weighting (`* 0.02`, `log1p`) leaves every tie-group order
    untouched, so an equality-style sentinel would pass while AD-11 was being
    violated. What a re-weighting CAN change is the order, and only if it is
    non-monotone - so those are the mutants worth pinning.
    """
    saving, value, clientnum = _population([5.0, 5.0, 5.0], [100.0, 900.0, 400.0], [1, 2, 3])

    honest = target_priority(saving, value, clientnum)
    reweighted = target_priority(saving, transform(value), clientnum)

    assert not honest.equals(reweighted)


def test_a_monotone_reweighting_is_invisible_here_and_this_file_says_so():
    """The limit of the test above, pinned so nobody claims more than it proves.

    `log1p` is monotone on non-negative value, so it cannot move a rank. AC7 is
    covered against non-monotone re-weighting only; a monotone one is caught by
    the AD-11 structure guard, not by this module.
    """
    saving, value, clientnum = _population([5.0, 5.0, 5.0], [100.0, 900.0, 400.0], [1, 2, 3])

    honest = target_priority(saving, value, clientnum)
    rescaled = target_priority(saving, np.log1p(value), clientnum)

    pd.testing.assert_series_equal(honest, rescaled)


# --- AC6 / D2: the non-negativity the ranking stands on ----------------------


def test_a_negative_customer_value_is_refused(distinct):
    saving, value, clientnum = distinct
    value = value.copy()
    value.iloc[0] = -1.0

    with pytest.raises(ValueError, match="non-negative"):
        target_priority(saving, value, clientnum)


def test_the_refusal_explains_why_rather_than_just_reporting_a_range():
    """The reason is monotonicity reversal, measured in story 3-2 (-35 vs -275).

    A message that only says "out of range" would invite a caller to clip the
    value and move on, which is precisely the wrong repair.
    """
    saving, value, clientnum = _population([5.0], [-1.0], [1])

    with pytest.raises(ValueError, match="monotonic"):
        target_priority(saving, value, clientnum)


# --- Input guards (the shape story 3-2 established) --------------------------


def test_an_empty_population_is_refused():
    saving, value, clientnum = _population([], [], [])

    with pytest.raises(ValueError, match="empty"):
        target_priority(saving, value, clientnum)


def test_a_duplicated_customer_is_refused():
    saving, value, clientnum = _population([5.0, 6.0], [10.0, 20.0], [7, 7])

    with pytest.raises(ValueError, match="duplicat"):
        target_priority(saving, value, clientnum)


def test_mismatched_lengths_are_reported_as_a_population_difference():
    saving, value, clientnum = _population([5.0, 6.0], [10.0, 20.0], [1, 2])

    with pytest.raises(ValueError, match="different populations"):
        target_priority(saving.iloc[:1], value, clientnum)


def test_a_clientnum_column_that_disagrees_with_the_index_is_refused():
    """Trap 4: two frames in different row orders both carry a RangeIndex.

    Measured on the real artifacts, `churn_scored.parquet` is NOT in the same
    row order as `bankchurners.parquet`, `Index.equals` returns True anyway,
    and the resulting total was 37% too high with nothing raised. This function
    holds CLIENTNUM as a sort key, which makes it the first place the labels
    can be compared against the index at all.
    """
    index = pd.Index([1, 2, 3], name="CLIENTNUM")
    saving = pd.Series([1.0, 2.0, 3.0], index=index)
    value = pd.Series([10.0, 20.0, 30.0], index=index)
    clientnum = pd.Series([3, 2, 1], index=index, name="CLIENTNUM")

    with pytest.raises(ValueError, match="disagrees"):
        target_priority(saving, value, clientnum)


def test_a_non_series_input_names_the_argument():
    saving, value, clientnum = _population([5.0], [10.0], [1])

    with pytest.raises(ValueError, match="expected_saving"):
        target_priority(saving.to_frame(), value, clientnum)


def test_missing_entries_are_refused(distinct):
    saving, value, clientnum = distinct
    saving = saving.copy()
    saving.iloc[0] = np.nan

    with pytest.raises(ValueError, match="missing"):
        target_priority(saving, value, clientnum)


# --- AC2 / AC5 / D1: selection cuts on budget AND on sign -------------------


def test_the_budget_binds_when_it_buys_fewer_than_the_positive_candidates(distinct):
    saving, value, clientnum = distinct

    result = select_within_budget(
        saving, value, clientnum, budget=2 * COST_PER_CONTACT, cost_per_contact=COST_PER_CONTACT
    )

    assert result.selected_count == 2
    assert result.binding_constraint == "budget"
    assert result.selected.loc[[1, 2]].all()
    assert not result.selected.loc[[3, 4]].any()


def test_a_budget_large_enough_for_everyone_still_stops_at_the_last_positive(
    distinct,
):
    """D1's core claim: an unspent budget is not a reason to destroy value."""
    saving, value, clientnum = distinct

    result = select_within_budget(
        saving, value, clientnum, budget=1_000_000.0, cost_per_contact=COST_PER_CONTACT
    )

    assert result.selected_count == 3
    assert result.positive_candidates == 3
    assert result.binding_constraint == "positivity"
    assert not result.selected.loc[3]


def test_the_selected_total_is_maximal_at_the_positivity_cut(distinct):
    """Buying one more than the positives lowers the total - the reason for D1."""
    saving, value, clientnum = distinct

    result = select_within_budget(saving, value, clientnum, budget=1_000_000.0)

    everyone = saving.sum()
    assert result.selected_total > everyone


def test_every_negative_saving_ranks_below_every_positive_one(distinct):
    """The invariant the positivity cut actually rests on.

    Because the primary sort key IS the expected saving, the top
    `positive_candidates` ranks are exactly the positive customers. That makes
    `selected_count = min(affordable, positive_candidates)` sufficient on its
    own, and it is why the `& is_positive` mask in `select_within_budget` is an
    EQUIVALENT mutant - removing it changes no behaviour (verified by mutation
    run M5, story 3-3). The mask is kept as defence in depth against a wrong
    `selected_count`, and this test pins the invariant that makes the two
    formulations agree. If the ranking ever stopped leading with the saving,
    this test would fail FIRST and the mask would become load-bearing.
    """
    saving, value, clientnum = distinct

    ranks = target_priority(saving, value, clientnum)

    assert ranks[saving > 0].max() < ranks[saving <= 0].min()


def test_selection_is_a_prefix_of_the_priority_order(distinct):
    """Nothing may be bought out of order - the rank IS the policy."""
    saving, value, clientnum = distinct

    result = select_within_budget(saving, value, clientnum, budget=2 * COST_PER_CONTACT)

    chosen_ranks = sorted(result.priority[result.selected].tolist())
    assert chosen_ranks == [1, 2]


def test_no_selected_customer_ever_has_a_non_positive_saving(distinct):
    """The contract D1 actually promises, stated independently of HOW it holds.

    Two mechanisms enforce it - the `min()` in `selected_count` and the
    `is_positive` mask - and either alone is sufficient today. This assertion
    is written against the OUTCOME so it survives a change to either one.
    Verified by mutation: removing both (run M10) buys a negative customer and
    drops the campaign total from 15.0 to 13.0.
    """
    saving, value, clientnum = distinct

    for budget in (0.0, COST_PER_CONTACT, 2 * COST_PER_CONTACT, 1_000_000.0):
        result = select_within_budget(saving, value, clientnum, budget=budget)
        assert (saving[result.selected] > 0.0).all()


def test_the_selected_column_is_named_for_the_mart(distinct):
    saving, value, clientnum = distinct

    result = select_within_budget(saving, value, clientnum, budget=2 * COST_PER_CONTACT)

    assert result.selected.name == SELECTED_COLUMN
    assert result.priority.name == PRIORITY_COLUMN


# --- AC4: an empty selection must say WHY (P1 2-1) --------------------------


def test_a_zero_budget_is_reported_as_a_zero_budget_not_as_no_candidates(distinct):
    saving, value, clientnum = distinct

    result = select_within_budget(saving, value, clientnum, budget=0.0)

    assert result.selected_count == 0
    assert result.binding_constraint == ZERO_BUDGET
    assert result.positive_candidates == 3


def test_a_budget_below_one_contact_is_reported_as_a_zero_budget(distinct):
    saving, value, clientnum = distinct

    result = select_within_budget(
        saving, value, clientnum, budget=COST_PER_CONTACT - 0.01, cost_per_contact=COST_PER_CONTACT
    )

    assert result.affordable_contacts == 0
    assert result.binding_constraint == ZERO_BUDGET


def test_a_population_with_no_positive_saving_is_reported_as_such():
    """The other empty result, and it is NOT the same fact as an empty budget."""
    saving, value, clientnum = _population([-1.0, -2.0], [10.0, 20.0], [1, 2])

    result = select_within_budget(saving, value, clientnum, budget=1_000_000.0)

    assert result.selected_count == 0
    assert result.binding_constraint == NO_POSITIVE_CANDIDATES
    assert result.affordable_contacts > 0


def test_the_two_empty_outcomes_are_distinguishable(distinct):
    """AC4 in one assertion: 'nothing selected' is not one fact but two."""
    saving, value, clientnum = distinct
    barren_saving, barren_value, barren_clientnum = _population(
        [-1.0, -2.0], [10.0, 20.0], [1, 2]
    )

    broke = select_within_budget(saving, value, clientnum, budget=0.0)
    barren = select_within_budget(
        barren_saving, barren_value, barren_clientnum, budget=1_000_000.0
    )

    assert broke.binding_constraint != barren.binding_constraint


def test_an_empty_selection_still_returns_a_full_priority_column(distinct):
    """A silent empty frame would drop the ranking that the mart still needs."""
    saving, value, clientnum = distinct

    result = select_within_budget(saving, value, clientnum, budget=0.0)

    assert len(result.priority) == len(saving)
    assert not result.selected.any()


def test_a_negative_budget_is_refused(distinct):
    saving, value, clientnum = distinct

    with pytest.raises(ValueError, match="non-negative"):
        select_within_budget(saving, value, clientnum, budget=-1.0)


def test_a_non_finite_budget_is_refused(distinct):
    saving, value, clientnum = distinct

    with pytest.raises(ValueError, match="finite"):
        select_within_budget(saving, value, clientnum, budget=float("nan"))


def test_a_zero_cost_per_contact_is_refused(distinct):
    """At zero cost the budget stops being a constraint and 'top N' is a lie."""
    saving, value, clientnum = distinct

    with pytest.raises(ValueError, match="cost_per_contact"):
        select_within_budget(saving, value, clientnum, budget=10.0, cost_per_contact=0.0)


# --- AC2: the random baseline (AD-7, and trap 3) ----------------------------


def test_the_baseline_is_reproducible_for_a_fixed_seed(distinct):
    saving, _, _ = distinct

    first = random_baseline(saving, n_contacts=2, draws=32, seed=RANDOM_SEED)
    second = random_baseline(saving, n_contacts=2, draws=32, seed=RANDOM_SEED)

    assert first.mean_total == second.mean_total
    assert first.spread_total == second.spread_total


def test_a_different_seed_gives_a_different_baseline(distinct):
    """If this passed by accident the seed would not be reaching the sampler."""
    saving, _, _ = distinct

    first = random_baseline(saving, n_contacts=2, draws=8, seed=RANDOM_SEED)
    second = random_baseline(saving, n_contacts=2, draws=8, seed=RANDOM_SEED + 1)

    assert first.mean_total != second.mean_total


def test_more_draws_shrink_the_spread_of_the_mean(distinct):
    """Trap 3: the point of averaging is that ONE draw is not a fact.

    Compares the spread of the per-draw totals, which is what the report has to
    print alongside the multiple.
    """
    saving, _, _ = distinct

    few = [random_baseline(saving, n_contacts=2, draws=4, seed=s).mean_total for s in range(20)]
    many = [random_baseline(saving, n_contacts=2, draws=256, seed=s).mean_total for s in range(20)]

    assert np.std(many) < np.std(few)


def test_the_baseline_records_how_many_draws_produced_it(distinct):
    """A mean with no draw count cannot be audited (trap 3)."""
    saving, _, _ = distinct

    baseline = random_baseline(saving, n_contacts=2, draws=64, seed=RANDOM_SEED)

    assert baseline.draws == 64
    assert baseline.seed == RANDOM_SEED
    assert baseline.n_contacts == 2


def test_the_full_population_baseline_equals_the_total(distinct):
    """Sampling everyone is not random any more - the multiple must be 1.0."""
    saving, value, clientnum = distinct

    baseline = random_baseline(saving, n_contacts=len(saving), draws=8, seed=RANDOM_SEED)

    assert baseline.mean_total == pytest.approx(saving.sum())
    assert baseline.spread_total == pytest.approx(0.0)


def test_targeting_beats_random_on_a_population_with_spread(distinct):
    saving, value, clientnum = distinct
    result = select_within_budget(saving, value, clientnum, budget=2 * COST_PER_CONTACT)
    baseline = random_baseline(saving, n_contacts=result.selected_count, draws=256, seed=RANDOM_SEED)

    multiple = multiple_over_random(result.selected_total, baseline)

    assert multiple > 1.0


def test_the_multiple_is_refused_when_the_baseline_is_not_positive():
    """A ratio against a zero or negative denominator is not a multiple.

    Reporting -3.2x as "3.2 times better" is the failure this guard prevents.
    """
    saving, value, clientnum = _population([-1.0, -2.0, -3.0], [10.0, 20.0, 30.0], [1, 2, 3])
    baseline = random_baseline(saving, n_contacts=2, draws=8, seed=RANDOM_SEED)

    with pytest.raises(ValueError, match="multiple"):
        multiple_over_random(-1.0, baseline)


def test_asking_for_more_contacts_than_customers_is_refused(distinct):
    saving, _, _ = distinct

    with pytest.raises(ValueError, match="n_contacts"):
        random_baseline(saving, n_contacts=len(saving) + 1, draws=8, seed=RANDOM_SEED)


def test_zero_draws_are_refused(distinct):
    saving, _, _ = distinct

    with pytest.raises(ValueError, match="draws"):
        random_baseline(saving, n_contacts=2, draws=0, seed=RANDOM_SEED)


# --- Purity (AD-1/AD-9) -----------------------------------------------------


def test_the_inputs_are_never_modified(distinct):
    saving, value, clientnum = distinct
    before = (saving.copy(), value.copy(), clientnum.copy())

    select_within_budget(saving, value, clientnum, budget=2 * COST_PER_CONTACT)

    pd.testing.assert_series_equal(saving, before[0])
    pd.testing.assert_series_equal(value, before[1])
    pd.testing.assert_series_equal(clientnum, before[2])
