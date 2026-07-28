"""The dashboard spec is a CONTRACT, and these tests are its guard (story 4-3).

The workbook is built by a human from `marts/dashboard-spec.md` alone
(conventions 7: the session cannot run Tableau), so the document is the last
machine-checkable layer before the screen. What gets pinned here:

  - the EXPOSED-FIELD table names only real mart columns, with valid tab
    numbers (a spec'd field or tab that does not exist would fail silently at
    workbook build time, far from here),
  - `churn_score` never appears as an exposed field (D2 - the +19% swap has no
    guard in a BI dropdown, hiding the column is the defence),
  - the three prohibition clauses, ALL FOUR AD-3 scenario items (the 4-3 code
    review found exactly the deviated item missing from the assertions), and
    the SHAP-is-not-causal caption rule are present verbatim.

Slicing discipline (4-1b + 4-3 review lessons): every slice asserts BOTH its
anchors exist - a lost END anchor would otherwise make `find` return -1 and the
slice silently widen to the whole document, degrading a scoped assertion into a
full-text search.
"""

from __future__ import annotations

import re
from pathlib import Path

from crm.marts.customers import MART_COLUMNS

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DOC = REPO_ROOT / "marts" / "dashboard-spec.md"

# The workbook's tab universe: 4 official tabs + the dedicated scenario tab.
_VALID_TABS = {"1", "2", "3", "5"}  # tab 4 is the frozen LTV stub - no fields


def _spec_text() -> str:
    return SPEC_DOC.read_text(encoding="utf-8")


def _slice(start_anchor: str, end_anchor: str | None = None) -> str:
    """A scoped slice whose anchors MUST both exist.

    `find` returning -1 for a lost END anchor would make `text[start:-1]` cover
    the rest of the document, so a renamed heading silently degrades every
    assertion inside into a full-text search (4-3 code review E1/M2).
    """
    text = _spec_text()
    start = text.find(start_anchor)
    assert start != -1, f"dashboard spec lost its '{start_anchor}' anchor"
    if end_anchor is None:
        return text[start:]
    end = text.find(end_anchor, start + 1)
    assert end != -1, f"dashboard spec lost its '{end_anchor}' anchor"
    return text[start:end]


def _section(heading: str) -> str:
    """One `## `-level section body, matched at line start (a `### x` heading
    contains `## x` as a substring - level must be anchored, review E7)."""
    text = _spec_text()
    match = re.search(rf"^## {re.escape(heading)}", text, flags=re.MULTILINE)
    assert match, f"dashboard spec lost its '{heading}' section"
    end = text.find("\n## ", match.start() + 1)
    return text[match.start():end] if end != -1 else text[match.start():]


def _preamble() -> str:
    """Everything before the first `## ` section - where the AD-3 role
    boundary and the screenshot rule live (review M3: previously untested)."""
    text = _spec_text()
    end = text.find("\n## ")
    assert end != -1
    return text[:end]


def _field_rows() -> list[tuple[str, str]]:
    """(field, tab-cell) pairs from the exposed-fields table."""
    section = _section("노출 필드")
    return re.findall(r"^\| `(\w+)` \| ([^|]+) \|", section, flags=re.MULTILINE)


def _exposed_fields() -> list[str]:
    return [field for field, _tabs in _field_rows()]


# --- AC7: the exposed-field table against the real mart ----------------------


def test_every_exposed_field_is_a_real_mart_column() -> None:
    """A spec'd field that does not exist fails at workbook build time, with
    nobody at the keyboard who can read this repo - so it fails here instead."""
    exposed = _exposed_fields()

    assert exposed, "exposed-field table parsed to nothing - check the format"
    assert set(exposed) <= set(MART_COLUMNS), (
        f"spec exposes non-mart fields: {set(exposed) - set(MART_COLUMNS)}"
    )


def test_churn_score_is_never_an_exposed_field() -> None:
    """D2: the +19% column swap has no guard in a BI dropdown. The mart keeps
    both columns (audit layer); the screen hides the ranking one (misuse
    layer). This is the split 3-0 D3 proposed, finished."""
    assert "churn_score" not in _exposed_fields()


def test_the_hidden_field_clause_names_churn_score_and_the_reason() -> None:
    section = _section("노출 필드")

    assert "숨김 필드" in section
    assert "`churn_score`" in section
    assert "+19.0%" in section  # the measured cost of the swap, not vibes


def test_exactly_the_nine_public_columns_are_exposed() -> None:
    """Every mart column except churn_score is exposed - a column silently
    dropped from the spec would hide auditable data from the workbook."""
    expected = [column for column in MART_COLUMNS if column != "churn_score"]

    assert sorted(_exposed_fields()) == sorted(expected)


def test_the_tab_cells_name_only_tabs_that_exist() -> None:
    """Review M1/E3: the tab column was unparsed, so '2, 3' could claim a tab
    the body never specs (or tab 4, which is a stub with no data). Every token
    must be a real tab, and the AD-3 (4) fields must include the scenario tab."""
    rows = dict(_field_rows())

    for field, tab_cell in rows.items():
        tabs = {token.strip() for token in tab_cell.split(",")}
        assert tabs <= _VALID_TABS, f"{field}: unknown tab(s) {tabs - _VALID_TABS}"
    # AD-3 item 4 needs the official thresholds VISIBLE on the scenario tab.
    assert "5" in rows["threshold_official_risk"]
    assert "5" in rows["threshold_official_value"]


# --- AC3: the role boundary lives in the preamble (review M3) ----------------


def test_the_preamble_declares_the_bi_role_boundary_and_screenshot_rule() -> None:
    preamble = _preamble()

    assert "BI는 표시하며 재계산하지 않는다" in preamble
    assert "공식 뷰에서만" in preamble  # screenshots


# --- AC7: the three prohibition clauses --------------------------------------


def test_the_prohibition_clauses_are_present() -> None:
    section = _section("금지 조항")

    assert "마트 조인 금지" in section  # AD-2
    assert "`_official` 재계산 금지" in section  # AD-3
    assert "risk_quantile annex 반입 금지" in section  # Sally B8


def test_the_annex_clause_bans_every_import_form() -> None:
    """B8's exact worry: the annex arriving as a parameter would look harmless
    and still soften 'one official 2x2' on screen."""
    section = _section("금지 조항")

    assert "탭·시트·파라미터 어느 형태로도" in section


def test_the_parameter_rule_bans_quadrant_definition_not_the_budget() -> None:
    """Review H1/F3: the earlier wording ('rate·cost only') banned the spec's
    own budget parameter. The rule's INTENT is pinned instead: parameters that
    move the quadrant DEFINITION are banned, campaign-assumption parameters
    (budget, rate, cost) are allowed."""
    section = _section("금지 조항")

    assert "분면 정의를 바꾸는 파라미터" in section
    assert "예산·성공률·비용" in section


# --- AC2: scenario rules - all FOUR AD-3 items -------------------------------


def test_the_ad3_scenario_checklist_is_verbatim_all_four_items() -> None:
    """Review F1/F2/H2/E2: item 2 (different tab) was the one item the spec
    had softened AND the one item this test skipped. All four now pinned, in
    the epics wording."""
    section = _section("시나리오 뷰 규약 (AD-3 검사 가능 4항목 — 체크리스트)")

    assert "`[시나리오] `" in section  # 1. title prefix
    assert "공식 뷰와 다른 탭" in section  # 2. different tab - the deviated one
    assert "전용 탭(탭5)" in section  # ...and the design that satisfies it
    assert "다른 배경색" in section  # 3. background
    assert "현재 임계값과 공식 임계값을 병기" in section  # 4. epics wording
    assert "`_scenario` 접미" in section
    assert "`_official` 컬럼을 재계산하는 계산필드를 만들지 않는다" in section


def test_the_shap_caption_rule_carries_both_warnings() -> None:
    """A8 (epic-1, carried through two retros): the warning must reach the
    SCREEN layer, and a caption without it is declared a spec violation."""
    tab3 = _slice("### 탭3", "### 탭4")

    assert "인과가 아니다" in tab3
    assert "실측 아닌 제안" in tab3
    assert "사양 위반" in tab3
    assert "텍스트 캡션만" in tab3  # no SHAP numbers on a public screen


def test_the_caption_rule_is_declared_global_not_tab3_only() -> None:
    """Review F5: AC6 says '화면 어딘가에' - a caption on tab 2 mentioning an
    action must not escape the rule just because the rule lives in tab 3."""
    preamble = _preamble()

    assert "모든 시트의 캡션" in preamble
    assert "탭3에 한정되지 않는다" in preamble


# --- AC2/AC7: the campaign_selected scenario field ---------------------------


def test_the_scenario_selection_formula_matches_the_pinned_definition() -> None:
    """D3: the field VISUALISES the AD-12 definition the schema doc owns - both
    halves (rank within budget AND positive saving) must survive edits, or the
    scenario quietly becomes the top-N cut the schema's 금지 cell forbids."""
    sheet = _slice("### 탭5", "\n## ")

    assert "campaign_selected_scenario" in sheet
    assert "[target_priority] <= FLOOR([budget] / 5.0)" in sheet
    assert "[expected_saving] > 0" in sheet
    assert "정책가정" in sheet  # the 5.0 is an assumption, labelled
    assert "재계산이 아니다" in sheet  # AD-3 defence stated where the field is


def test_the_budget_parameter_domain_is_specified() -> None:
    """Review E4/E5/M5: the formula equals `select_within_budget` only on
    integer multiples-of-5 budgets (the code has _BUDGET_TOL, Tableau's FLOOR
    does not), and a negative budget must be inexpressible on screen (the code
    path REFUSES it - the screen must not silently show an empty sheet
    instead). The parameter spec is what carries both guarantees."""
    sheet = _slice("### 탭5", "\n## ")

    assert "정수" in sheet
    assert "최소 0" in sheet
    assert "1-base" in sheet  # the <= comparison depends on this
    assert "_BUDGET_TOL" in sheet  # the honest footnote about the divergence


def test_the_ltv_tab_is_a_frozen_stub_not_a_fabricated_spec() -> None:
    """D1: spec'ing sheets for data that does not exist would launder a frozen
    epic into a shipped one. The stub must say WHY it is empty, and must keep
    the no-join principle a stub edit could otherwise drop (review E9)."""
    tab4 = _slice("### 탭4", "### 탭5")

    assert "동결" in tab4
    assert "존재하지 않는다" in tab4
    assert "4-2 해동 시" in tab4
    assert "별도 데이터 원본" in tab4  # AD-2 survives the thaw


def test_the_anchor_table_carries_labelled_golden_values() -> None:
    """Review E6: the anchor table is what the workbook builder checks against,
    and unlabelled numbers cannot tell which quadrant is which. Values must
    match the golden asserts in test_customers.py - the same dual-update
    contract the schema doc carries."""
    section = _section("검산 앵커 (워크북 제작 후 대조)")

    assert "low_cost_keep 4,624" in section
    assert "accept_churn 2,971" in section
    assert "watch 2,089" in section
    assert "save_first 443" in section
    assert "10,127" in section
    assert "0.132753" in section
    assert "1,454,088" in section
