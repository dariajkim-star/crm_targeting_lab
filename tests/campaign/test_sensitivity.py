"""Behavioural tests for the sensitivity sweep (story 3-4, CAP-7/FR14).

Why these assertions and not others
-----------------------------------
The temptation this file resists is re-deriving `P*value*rate - cost` inside the
test and checking the module computes the same thing - which would prove only
that the same formula was typed twice (AD-9's rule, in test form; P1 2-2 shipped
a sign-flip exactly that way). Each test below pins a PROPERTY or a CONTRACT
instead:

  - REIMPLEMENTATION DETECTION (AC1, the core mutant). `sweep_sensitivity` must
    CONSUME `expected_saving`, never re-derive it. A sentinel monkeypatched over
    `expected_saving` must flow through untouched - if the module computed the
    grid itself, the sentinel would not appear and the test goes red. This is
    the 3-2 `test_the_value_input_is_used_exactly_as_given` method applied to
    the whole sweep.
  - CONFIG GRID GUARD, NOT DUPLICATED (AC2). The representative-in-grid
    invariant is owned by `crm/config.py`'s import-time `raise`; this file pins
    that the guard bites, and that sensitivity.py does not re-declare the grid
    or copy the constant check.
  - NO TIES ACROSS THE GRID (AC5/D3). The 3-3 hand-off predicted the grid floor
    would collapse savings into ties; measured, it never does, because `saving`
    is an affine transform of a distinct `P*value` and affine transforms
    preserve distinctness for rate > 0. Pinned as a property, and the real-data
    count (0 across all 25 points) is pinned separately where data is present.
  - QUADRANT SIGN IS THE CONCLUSION (D1). Robust quadrants keep one sign across
    the grid; fragile ones flip. Pinned on a synthetic fixture built to contain
    one of each, and on the real artifact's four-cell verdict where present.
  - BREAK-EVEN IS CONTINUOUS (함정 5). The rate that flips a quadrant is located
    by bisection on the SIGN of `expected_saving`, not by the formula, and lands
    off the coarse grid.
  - THE ANNEX IS A SCENARIO, NEVER OFFICIAL (AC7/AD-3). The risk_quantile sweep
    consumes `assign_quadrant`, produces DIFFERENT compositions per quantile,
    and writes nothing official or to disk.

Real-data oracles (537/443/348, the four-cell robust/fragile verdict, 0 ties)
are pinned in the `TestRealArtifact` block, skipped when the parquet is absent
so the property tests still run in a bare checkout.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crm.campaign import sensitivity as sensitivity_module
from crm.campaign.sensitivity import (
    GridCell,
    RiskQuantileAnnex,
    SensitivityGrid,
    quadrant_breakeven_rate,
    risk_quantile_annex,
    sweep_sensitivity,
)
from crm.config import (
    COST_GRID,
    COST_PER_CONTACT,
    DATA_DIR,
    QUADRANT_RULE,
    RETENTION_GRID,
    RETENTION_SUCCESS_RATE,
)

_SENSITIVITY_SOURCE = Path(sensitivity_module.__file__).read_text(encoding="utf-8")


def _frame(prob, value, labels, *, index=None):
    """Three aligned Series with a shared index (the sweep's precondition)."""
    idx = pd.Index(range(len(prob)) if index is None else index)
    return (
        pd.Series(prob, index=idx, name="churn_prob_calibrated", dtype=float),
        pd.Series(value, index=idx, name="customer_value", dtype=float),
        pd.Series(labels, index=idx, name="quadrant_official"),
    )


# --- AC1: the sweep consumes expected_saving, never re-derives it -------------


def test_sweep_flows_expected_saving_output_through_verbatim(monkeypatch):
    """AC1/AD-9 core mutant: a sentinel from expected_saving must survive.

    If `sweep_sensitivity` re-implemented the grid formula instead of calling
    `expected_saving`, this sentinel (which ignores rate and cost entirely)
    would never reach the cell totals and the assertion would fail.
    """
    prob, value, labels = _frame([0.5, 0.5, 0.5], [100.0, 100.0, 100.0], ["a", "a", "b"])
    sentinel = pd.Series([7.0, 11.0, -3.0], index=prob.index, name="expected_saving")

    calls = {"n": 0}

    def fake_expected_saving(p, v, *, retention_rate, cost_per_contact):
        calls["n"] += 1
        return sentinel

    monkeypatch.setattr(sensitivity_module, "expected_saving", fake_expected_saving)

    grid = sweep_sensitivity(
        prob, value, labels,
        retention_grid=(0.2, 0.4), cost_grid=(1.0, 5.0),
        representative=(0.2, 1.0),
    )

    # One call per grid point - the sweep re-CALLS the function, it does not
    # compute one Series and reuse it.
    assert calls["n"] == 4
    for cell in grid.cells:
        # Every cell reflects the sentinel: total = 7+11-3 = 15, positives = 18,
        # share positive = 2/3. None of these depend on rate/cost because the
        # sentinel does not - which is exactly what proves consumption.
        assert cell.total_net == pytest.approx(15.0)
        assert cell.total_positive == pytest.approx(18.0)
        assert cell.share_positive == pytest.approx(2 / 3)


def test_source_does_no_arithmetic_on_the_assumption_parameters():
    """AD-9 in source form: the module never computes ON rate or cost.

    A re-derivation of the break-even/saving formula would have to do arithmetic
    with `retention_rate` and `cost_per_contact` (multiply, subtract, divide).
    Instead they are only ever PASSED to `expected_saving`. Checked over BinOp
    nodes - prose in docstrings that merely writes `cost/rate` does not count,
    which is why this is AST-based rather than a substring grep.
    """
    tree = ast.parse(_SENSITIVITY_SOURCE)
    names_in_arithmetic = {
        node.id
        for binop in ast.walk(tree)
        if isinstance(binop, ast.BinOp)
        for node in ast.walk(binop)
        if isinstance(node, ast.Name)
    }
    assert "cost_per_contact" not in names_in_arithmetic
    assert "retention_rate" not in names_in_arithmetic


# --- AC2: the config grid guard bites and is not duplicated here --------------


def test_config_representative_grid_guard_bites():
    """AC2: pushing the representative value off the grid fails config import.

    The invariant lives in `crm/config.py` as an import-time `raise` (not an
    `assert`, so `python -O` cannot strip it). Re-executed here under a synthetic
    module name to prove it fires, exactly as the structure self-check does.
    """
    source = (Path(sensitivity_module.__file__).parents[2] / "crm" / "config.py").read_text(encoding="utf-8")
    assert "RETENTION_SUCCESS_RATE: float = 0.30" in source
    broken = source.replace("RETENTION_SUCCESS_RATE: float = 0.30", "RETENTION_SUCCESS_RATE: float = 0.33")

    with pytest.raises(ValueError, match="AD-4"):
        exec(
            compile(broken, "<patched-config>", "exec"),
            {
                "__name__": "crm.config_patched",
                "__file__": str(Path(sensitivity_module.__file__).parents[2] / "crm" / "config.py"),
            },
        )


def test_sensitivity_does_not_redeclare_the_grid_or_copy_the_guard():
    """AC2: sensitivity CONSUMES the config grid, it does not re-create it.

    A re-declared `RETENTION_GRID = (...)` or a copied representative-in-grid
    `raise` would be the AD-4 violation this story is meant to avoid: two
    sources of truth for the grid. The grid must arrive by import only.
    """
    tree = ast.parse(_SENSITIVITY_SOURCE)
    assigned_names = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "RETENTION_GRID" not in assigned_names
    assert "COST_GRID" not in assigned_names
    # The representative check the sweep DOES make is about its own ARGUMENT
    # against the PASSED grid, not a re-statement of the config constant guard;
    # it never mentions RETENTION_SUCCESS_RATE as a literal to re-verify.
    assert "RETENTION_SUCCESS_RATE not in" not in _SENSITIVITY_SOURCE


def test_sweep_rejects_representative_off_the_passed_grid():
    """The sweep's own argument check: headline must lie on the sweep (AD-4)."""
    prob, value, labels = _frame([0.5, 0.5], [100.0, 100.0], ["a", "b"])
    with pytest.raises(ValueError, match="representative"):
        sweep_sensitivity(
            prob, value, labels,
            retention_grid=(0.2, 0.4), cost_grid=(1.0, 5.0),
            representative=(0.3, 1.0),  # 0.3 is not on (0.2, 0.4)
        )


# --- AC5 / D3: no ties form anywhere on the grid ------------------------------


def test_grid_produces_no_ties_when_value_at_risk_is_distinct():
    """AC5/D3: distinct P*value stays distinct under every affine (rate, cost).

    Built so `P*value` is 5 distinct numbers; the sweep must report 0 ties in
    every cell, because `saving = P*value*rate - cost` is a strictly monotone
    affine map for rate > 0.
    """
    prob = [0.1, 0.2, 0.3, 0.4, 0.5]
    value = [100.0, 100.0, 100.0, 100.0, 100.0]  # P*value = 10,20,30,40,50 distinct
    p, v, labels = _frame(prob, value, ["a"] * 5)

    grid = sweep_sensitivity(
        p, v, labels,
        retention_grid=RETENTION_GRID, cost_grid=COST_GRID,
        representative=(RETENTION_SUCCESS_RATE, COST_PER_CONTACT),
    )

    assert all(cell.ties == 0 for cell in grid.cells)
    assert all(cell.distinct_savings == 5 for cell in grid.cells)


def test_affine_preservation_holds_symbolically():
    """The reason ties never form, checked without re-running the sweep.

    A direct statement of the D3 argument on a controlled vector: an affine
    transform with a non-zero slope maps distinct inputs to distinct outputs.
    Not a re-implementation of the sweep - a property of the arithmetic it
    relies on.
    """
    var = np.array([10.0, 20.0, 30.0, 40.0, 50.0])  # distinct value-at-risk
    for rate in RETENTION_GRID:
        for cost in COST_GRID:
            saving = var * rate - cost
            assert len(np.unique(saving)) == len(var)


# --- D1: robust vs fragile quadrants ------------------------------------------


@pytest.fixture
def mixed_quadrants():
    """A fixture with one ROBUST and one FRAGILE quadrant across the grid.

    `hi` customers have large value-at-risk, so their mean saving stays positive
    even at the worst (rate, cost). `lo` customers have tiny value-at-risk, so
    their mean saving is negative at high cost / low rate and positive at low
    cost / high rate - it flips.
    """
    prob = [0.5, 0.5, 0.5, 0.5]
    value = [1000.0, 1000.0, 20.0, 20.0]  # P*value = 500,500,10,10
    labels = ["hi", "hi", "lo", "lo"]
    return _frame(prob, value, labels)


def test_robust_quadrant_never_flips_and_fragile_one_does(mixed_quadrants):
    """D1: the sign of a quadrant mean is the conclusion, and only some flip."""
    prob, value, labels = mixed_quadrants
    grid = sweep_sensitivity(
        prob, value, labels,
        retention_grid=RETENTION_GRID, cost_grid=COST_GRID,
        representative=(RETENTION_SUCCESS_RATE, COST_PER_CONTACT),
    )
    by_label = {q.label: q for q in grid.quadrants}

    assert by_label["hi"].robust is True
    assert by_label["hi"].cells_positive == 25
    assert by_label["lo"].robust is False
    assert 0 < by_label["lo"].cells_positive < 25
    assert grid.robust_quadrants == (by_label["hi"],)
    assert grid.fragile_quadrants == (by_label["lo"],)


def test_representative_cell_is_present_and_self_describing(mixed_quadrants):
    """The grid guarantees its headline cell exists (AD-4, self-description)."""
    prob, value, labels = mixed_quadrants
    grid = sweep_sensitivity(
        prob, value, labels,
        retention_grid=RETENTION_GRID, cost_grid=COST_GRID,
        representative=(RETENTION_SUCCESS_RATE, COST_PER_CONTACT),
    )
    cell = grid.representative_cell()
    assert cell.retention_rate == RETENTION_SUCCESS_RATE
    assert cell.cost_per_contact == COST_PER_CONTACT


# --- 함정 5: break-even is a continuous curve, located by sign ----------------


def test_break_even_rate_is_found_off_grid_by_sign():
    """함정 5: the flip rate is continuous and located by bisecting the sign.

    Construct a quadrant with mean value-at-risk exactly 10 (P*value = 10 for
    every member), so its mean saving is `10*rate - cost`, zero at
    `rate = cost/10`. At cost 3 the break-even rate is 0.30 - a grid point by
    coincidence here; at cost 3.7 it is 0.37, which is NOT on the grid. The
    finder must return the analytic root without ever using the formula.
    """
    prob = [0.5, 0.5, 0.5]
    value = [20.0, 20.0, 20.0]  # P*value = 10 each
    p, v, labels = _frame(prob, value, ["q", "q", "q"])

    root_3 = quadrant_breakeven_rate(p, v, labels, "q", cost_per_contact=3.0)
    root_37 = quadrant_breakeven_rate(p, v, labels, "q", cost_per_contact=3.7)

    assert root_3 == pytest.approx(0.30, abs=1e-6)
    assert root_37 == pytest.approx(0.37, abs=1e-6)


def test_break_even_returns_none_when_quadrant_never_flips():
    """A quadrant with no sign change in the bracket has no break-even to report.

    Value-at-risk is 0.5 per member, so `0.5*rate - cost` is negative for every
    rate in (0, 1] at cost 1.0 - never worth contacting. The finder returns
    None rather than fabricating a rate outside the bracket.
    """
    prob = [0.5, 0.5]
    value = [1.0, 1.0]  # P*value = 0.5: below break-even at any rate for cost 1.0
    p, v, labels = _frame(prob, value, ["q", "q"])

    assert quadrant_breakeven_rate(p, v, labels, "q", cost_per_contact=1.0) is None


# --- AC7 / AD-3: the risk_quantile annex is a scenario, never official --------


@pytest.fixture
def score_frame():
    """100 customers with distinct scores and a clean high/low value split."""
    idx = pd.Index(range(100))
    score = pd.Series(np.linspace(0.01, 0.99, 100), index=idx, name="churn_score")
    value = pd.Series(np.linspace(100.0, 1000.0, 100), index=idx, name="customer_value")
    return score, value


def test_annex_compositions_differ_by_quantile(score_frame):
    """AC7/D2: different risk_quantile => different cell sizes (a scenario).

    Not a re-computation of assign_quadrant: it asserts the STRUCTURAL property
    the annex exists to show - the definition moves the composition - and that
    the cuts increase monotonically with the quantile.
    """
    score, value = score_frame
    annex = risk_quantile_annex(score, value, risk_quantiles=(0.70, 0.75, 0.80))

    save_first = [annex.composition(q).count("save_first") for q in (0.70, 0.75, 0.80)]
    cuts = [annex.composition(q).risk_cut for q in (0.70, 0.75, 0.80)]

    # A higher risk cut admits FEWER customers to the high-risk cells.
    assert save_first[0] > save_first[1] > save_first[2]
    assert cuts[0] < cuts[1] < cuts[2]
    assert annex.official_quantile == QUADRANT_RULE.risk_quantile


def test_annex_reports_zero_for_an_emptied_cell_not_keyerror(score_frame):
    """F1: an extreme risk_quantile can empty a cell - report 0, not raise.

    At risk_quantile 0.99 almost everyone falls below the risk cut, so a
    high-risk cell empties - here `watch` (the single top-scoring customer is
    high value, so it lands in `save_first`, leaving `watch` at zero).
    `value_counts` drops the absent label; the annex must still report the full
    four-cell composition with a 0, and `count()` must not KeyError.
    """
    score, value = score_frame
    annex = risk_quantile_annex(score, value, risk_quantiles=(0.99,))
    comp = annex.composition(0.99)

    # All four official cells are present; the emptied cell reads 0.
    labels = {name for name, _ in comp.counts}
    assert labels == {"save_first", "watch", "low_cost_keep", "accept_churn"}
    assert comp.count("watch") == 0  # would have KeyError'd before the fix
    # The composition still sums to the whole population - nobody vanished.
    assert sum(n for _, n in comp.counts) == len(score)


def test_annex_writes_nothing_official_or_to_disk(score_frame, tmp_path, monkeypatch):
    """AC7/AD-3: the annex persists nothing - no official column, no file.

    Runs with the cwd moved to an empty tmp dir and asserts no file appears, and
    that the module source contains neither `to_parquet` nor a `quadrant_official`
    write. The annex is a report input, not a mart.
    """
    score, value = score_frame
    monkeypatch.chdir(tmp_path)

    annex = risk_quantile_annex(score, value)

    assert isinstance(annex, RiskQuantileAnnex)
    assert list(tmp_path.iterdir()) == []  # nothing written

    # No persistence call anywhere in the module (AST, so docstring prose that
    # explains AD-3 does not count as a write).
    tree = ast.parse(_SENSITIVITY_SOURCE)
    write_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert write_calls.isdisjoint({"to_parquet", "to_csv", "to_feather", "write_text", "write_bytes"})
    # No string literal is emitted as an official column name.
    official_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "quadrant_official"
    ]
    assert official_literals == []


# --- Structural: the module carries no self-cut (mirrors the guard) -----------


def test_module_calls_no_quantile_percentile_or_median():
    """AC6 in the module's own AST: sensitivity.py forms no threshold itself.

    The structure guard `find_sensitivity_selfcut_violations` enforces this on
    the repo; this is the unit-level companion so a regression is caught in this
    file too.
    """
    tree = ast.parse(_SENSITIVITY_SOURCE)
    forbidden = {"quantile", "percentile", "median"}
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert forbidden.isdisjoint(calls)


# --- Real-data oracles (skipped without the parquet) --------------------------


def _load_real_frame():
    bank_path = DATA_DIR / "bankchurners.parquet"
    scored_path = DATA_DIR / "churn_scored.parquet"
    if not bank_path.exists() or not scored_path.exists():
        pytest.skip("real artifact parquet not present")
    from crm.segment.value import customer_value

    bank = pd.read_parquet(bank_path)
    scored = pd.read_parquet(scored_path)
    value = customer_value(bank)
    value.index = pd.Index(bank["CLIENTNUM"], name="CLIENTNUM")
    scored = scored.set_index(pd.Index(scored["CLIENTNUM"], name="CLIENTNUM")).loc[value.index]
    prob = scored["churn_prob_calibrated"].rename("churn_prob_calibrated")
    prob.index = value.index
    score = scored["churn_score"]
    score.index = value.index
    return prob, value, score


class TestRealArtifact:
    """Oracles that only the real artifact can pin (skipped when absent)."""

    def test_grid_has_zero_ties_and_the_four_cell_verdict(self):
        prob, value, score = _load_real_frame()
        labels = sensitivity_module.assign_quadrant(score, value).labels
        grid = sweep_sensitivity(prob, value, labels)

        # D3: zero ties across all 25 points.
        assert sum(cell.ties for cell in grid.cells) == 0
        # D1: the four-cell robust/fragile verdict.
        by_label = {q.label: q for q in grid.quadrants}
        assert by_label["save_first"].cells_positive == 25
        assert by_label["watch"].cells_positive == 25
        assert 0 < by_label["low_cost_keep"].cells_positive < 25
        assert 0 < by_label["accept_churn"].cells_positive < 25
        assert {q.label for q in grid.robust_quadrants} == {"save_first", "watch"}
        assert {q.label for q in grid.fragile_quadrants} == {"low_cost_keep", "accept_churn"}

    def test_risk_quantile_annex_matches_measured_counts(self):
        prob, value, score = _load_real_frame()
        annex = risk_quantile_annex(score, value, risk_quantiles=(0.70, 0.75, 0.80))

        # Measured (preinvest_3_4.py, artifact 9e1a4d71800f).
        assert annex.composition(0.70).count("save_first") == 537
        assert annex.composition(0.75).count("save_first") == 443
        assert annex.composition(0.80).count("save_first") == 348

    def test_representative_share_positive_is_the_reported_84_8_percent(self):
        prob, value, score = _load_real_frame()
        labels = sensitivity_module.assign_quadrant(score, value).labels
        grid = sweep_sensitivity(prob, value, labels)

        cell = grid.representative_cell()
        # 84.79% at (0.30, 5.0) - one CELL's conditional figure, not a fact.
        assert cell.share_positive == pytest.approx(0.8479, abs=5e-4)
