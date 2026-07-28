"""The dashboard spec is a CONTRACT, and these tests are its guard (story 4-3).

The workbook is built by a human from `marts/dashboard-spec.md` alone
(conventions 7: the session cannot run Tableau), so the document is the last
machine-checkable layer before the screen. What gets pinned here:

  - the EXPOSED-FIELD table names only real mart columns (a spec'd field that
    does not exist would fail silently at workbook build time, far from here),
  - `churn_score` never appears as an exposed field (D2 - the +19% swap has no
    guard in a BI dropdown, hiding the column is the defence),
  - the three prohibition clauses, the AD-3 scenario checklist, and the
    SHAP-is-not-causal caption rule are present VERBATIM - each one closes a
    named handover (Sally A8/B8, 3-0 D3), and prose that drifts loses the
    contract.

Assertions are section- or row-scoped, not whole-document (4-1b review lesson:
whole-text searches pass on strings that pre-exist elsewhere).
"""

from __future__ import annotations

import re
from pathlib import Path

from crm.marts.customers import MART_COLUMNS

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DOC = REPO_ROOT / "marts" / "dashboard-spec.md"


def _spec_text() -> str:
    return SPEC_DOC.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    """One `## `-level section body, scoped to the next same-level heading."""
    text = _spec_text()
    start = text.find(f"## {heading}")
    assert start != -1, f"dashboard spec lost its '{heading}' section"
    end = text.find("\n## ", start + 1)
    return text[start:end] if end != -1 else text[start:]


def _exposed_fields() -> list[str]:
    """Field names from the exposed-fields table (the single source)."""
    section = _section("노출 필드")
    return re.findall(r"^\| `(\w+)` \|", section, flags=re.MULTILINE)


# --- AC7-1/2: the exposed-field table against the real mart ------------------


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


# --- AC7-3: the three prohibition clauses ------------------------------------


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


# --- AC7-4: scenario rules and the causal warning ----------------------------


def test_the_ad3_scenario_checklist_is_verbatim() -> None:
    section = _section("시나리오 뷰 규약 (AD-3 검사 가능 4항목 — 체크리스트)")

    assert "`[시나리오] `" in section  # 1. title prefix
    assert "다른 배경색" in section  # 3. background
    assert "공식 값을 병기" in section  # 4. official beside current
    assert "`_scenario` 접미" in section
    assert "`_official` 컬럼을 재계산하는 계산필드를 만들지 않는다" in section


def test_the_shap_caption_rule_carries_both_warnings() -> None:
    """A8 (epic-1, carried through two retros): the warning must reach the
    SCREEN layer, and a caption without it is declared a spec violation."""
    text = _spec_text()
    # Heading-anchored: the preamble mentions 탭4 before 탭3's section exists,
    # so bare-substring anchors slice backwards to an empty string.
    tab3 = text[text.find("### 탭3"):text.find("### 탭4")]

    assert "인과가 아니다" in tab3
    assert "실측 아닌 제안" in tab3
    assert "사양 위반" in tab3
    assert "텍스트 캡션만" in tab3  # no SHAP numbers on a public screen


# --- AC7-5: the campaign_selected scenario field -----------------------------


def test_the_scenario_selection_formula_matches_the_pinned_definition() -> None:
    """D3: the field VISUALISES the AD-12 definition the schema doc owns - both
    halves (rank within budget AND positive saving) must survive edits, or the
    scenario quietly becomes the top-N cut the schema's 금지 cell forbids."""
    text = _spec_text()
    sheet = text[text.find("시트 2-2"):text.find("### 탭3")]

    assert "campaign_selected_scenario" in sheet
    assert "[target_priority] <= FLOOR([budget] / 5.0)" in sheet
    assert "[expected_saving] > 0" in sheet
    assert "정책가정" in sheet  # the 5.0 is an assumption, labelled
    assert "재계산이 아니다" in sheet  # AD-3 defence stated where the field is


def test_the_ltv_tab_is_a_frozen_stub_not_a_fabricated_spec() -> None:
    """D1: spec'ing sheets for data that does not exist would launder a frozen
    epic into a shipped one. The stub must say WHY it is empty."""
    text = _spec_text()
    start = text.find("### 탭4")
    assert start != -1, "dashboard spec lost its tab-4 stub"
    end = text.find("\n## ", start)
    tab4 = text[start:end] if end != -1 else text[start:]

    assert "동결" in tab4
    assert "존재하지 않는다" in tab4
    assert "4-2 해동 시" in tab4
