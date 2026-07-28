"""Public-release contract: the repo stays publishable (story 4-4, AD-10/NFR7).

Three surfaces are pinned:

  - the TREE never tracks a data/model artifact - by PATH PREFIX (data/,
    models/ are a closed set) and by suffix (the formats an artifact actually
    ships in). The commit-HISTORY scan is a one-time audit recorded in the
    story - history is immutable; what a regression guard must catch is a
    FUTURE artifact slipping in,
  - the README's headline numbers are built FROM `tests/marts/goldens.py` -
    the single source the mart tests also assert against - so a retrain that
    moves the mart turns the stale README red from one edit point (4-4 review
    H3/E6: hardcoded copies here would have been the fourth transcription),
  - the publish runbook keeps its verification steps.

Robustness (4-4 review E1/E2): git output is read as NUL-separated UTF-8 bytes
with quotepath off - the locale-decoded text mode let a non-ASCII path escape
the CSV check as an octal-escaped string (false green). No git / no repo /
timeout are SKIPS, not failures: an environment that cannot run the check is
not a violation, and reporting it as one buries real ones (D2 spirit).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.marts import goldens

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
RUNBOOK = REPO_ROOT / "docs" / "tableau-publish-runbook.md"

# Artifact formats a model/data file actually ships in (4-4 review E3: the
# original three left keras/numpy/arrow/sqlite/torch/xgboost-native wide open).
# The path-prefix assertion below is the closed set; this list is defence in
# depth for an artifact parked OUTSIDE data/ and models/.
_BANNED_SUFFIXES = (
    ".parquet", ".joblib", ".pkl", ".pickle", ".h5", ".npy", ".npz",
    ".feather", ".arrow", ".db", ".sqlite", ".duckdb", ".pt", ".pth",
    ".onnx", ".safetensors", ".ubj",
)
# Trees that must contain NO tracked file at all (gitignored by design; an
# extension list cannot cover xgboost's `model.json`, a path prefix can).
_BANNED_PREFIXES = ("data/", "models/")


def _tracked_files() -> list[str]:
    """`git ls-files`, NUL-separated, quotepath off, UTF-8 - or skip.

    Skips (not failures) when the environment cannot answer: git missing, a
    zip-download tree with no repo, or a timeout. `-z` + utf-8 bytes defeat
    the octal-escape false green (review E2).
    """
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            capture_output=True, cwd=REPO_ROOT, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("git unavailable - the tracked-file guard cannot run here")
    if result.returncode != 0:
        pytest.skip("not a git checkout - the tracked-file guard cannot run here")
    return [p for p in result.stdout.decode("utf-8").split("\0") if p]


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _readme_section(heading: str) -> str:
    """A `## `-level README section, BOTH anchors required (review E8: a lost
    end anchor silently widens the slice to the whole file, and stray numbers
    elsewhere then satisfy every assertion)."""
    text = _readme_text()
    match = re.search(rf"^## {re.escape(heading)}$", text, flags=re.MULTILINE)
    assert match, f"README lost its '{heading}' section"
    end = text.find("\n## ", match.start() + 1)
    assert end != -1, f"README section '{heading}' lost its closing anchor"
    return text[match.start():end]


# --- AC1: no data/model artifact is ever tracked -----------------------------


def test_no_tracked_file_lives_under_data_or_models() -> None:
    """The closed set: data/ and models/ are gitignored BY DESIGN, and an
    ignore file only advises - `git add -f` bypasses it silently. A path
    prefix catches what no extension list can (xgboost saves as .json)."""
    offenders = [
        path for path in _tracked_files()
        if path.startswith(_BANNED_PREFIXES)
    ]

    assert offenders == [], f"tracked files under data/ or models/: {offenders}"


def test_no_data_or_model_artifact_is_tracked_anywhere() -> None:
    """Defence in depth for an artifact parked outside the banned trees."""
    offenders = [
        path for path in _tracked_files()
        if path.lower().endswith(_BANNED_SUFFIXES)
    ]

    assert offenders == [], f"tracked data/model artifacts: {offenders}"


def test_the_only_tracked_csv_data_is_the_mart() -> None:
    """CSV needs a narrower rule: tooling manifests (.claude/_bmad) are fine,
    and the mart is the deliberate AD-2 exception. Set comparison (not list -
    git output order is not a contract), and NO fixture escape hatch: a new
    tracked CSV going red HERE is the intended friction - publishing rows
    nobody audited must be a conscious edit to this file (review E5 rejected)."""
    csvs = {
        path for path in _tracked_files()
        if path.lower().endswith(".csv")
        and not path.startswith((".claude/", "_bmad/"))
    }

    assert csvs == {"marts/mart_customers.csv"}, f"unexpected tracked CSVs: {csvs}"


# --- AC2/AC4: README headline numbers come FROM the goldens ------------------


def test_readme_headline_numbers_match_the_mart_goldens() -> None:
    """Built from `tests/marts/goldens.py`, not retyped (review H3/E6) - the
    README is a COPY and this test compares it against the source."""
    section = _readme_section("핵심 수치")

    assert goldens.ROW_COUNT_TEXT in section
    assert goldens.TOTAL_TEXT in section
    assert goldens.RISK_CUT_TEXT in section
    assert goldens.VALUE_CUT_TEXT in section
    for labelled in goldens.QUADRANT_TEXTS:
        assert labelled in section, f"README lost the labelled count '{labelled}'"
    assert goldens.PR_AUC in section
    assert goldens.PR_AUC_LIFT in section
    # H2: the model metric's source is NOT a committed file - the README must
    # say so instead of claiming everything in the table is committed.
    assert "재생성" in section


def test_readme_findings_numbers_are_pinned_too() -> None:
    """Auditor 결함5: the 발견 section quotes four measured figures; unguarded
    copies drift by the exact mechanism that bit the test-count cell."""
    section = _readme_section("발견 (요약)")

    assert "x17.27" in section
    assert "8,587" in section
    assert "+19.0%" in section
    assert "+37.2%" in section


def test_readme_states_all_four_assumptions() -> None:
    """성공신호 ④: every assumption named, none implied."""
    section = _readme_section("한계와 가정 (숨기지 않는 것)")

    assert "결합 불가" in section  # AD-1: the two datasets never join
    assert "단면" in section  # Attrition_Flag is a snapshot label
    assert "정책가정" in section  # 0.30 rate / 5.0 cost are assumed
    assert "GBP" in section  # currency: unitless customer lane, GBP LTV lane


def test_readme_admits_what_was_not_done() -> None:
    """정직성, SECTION-scoped (review E10: the whole-file scan passed on the
    word '동결' surviving anywhere - the honesty bullet itself was unguarded)."""
    section = _readme_section("한계와 가정 (숨기지 않는 것)")

    assert "동결" in section  # epic-2 / LTV demo not performed
    assert "테스트 수는 실행 환경" in section  # D2


def test_readme_carries_the_link_placeholder_or_a_public_link() -> None:
    """Review E11: runbook step 6 targets the placeholder string - it must
    exist until the day a real public link replaces it. Both states valid,
    absence of both is the defect."""
    text = _readme_text()

    assert ("퍼블리시 후 링크 기입" in text) or re.search(
        r"https://public\.tableau\.com/\S+", text
    ), "README has neither the link placeholder nor a published link"


# --- AC3/AC4: the runbook keeps its verification steps -----------------------


def test_runbook_exists_with_account_and_anchor_steps() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Tableau Public 계정" in text  # step 0 - OQ-5
    assert "검산 앵커" in text  # the workbook-vs-mart comparison step
    assert "공개 조회 가능" in text  # the publish disclosure
    assert "dashboard-spec.md" in text  # the spec is the build source


def test_runbook_carries_the_review_hardened_instructions() -> None:
    """4-4 review: the steps most likely to go wrong got explicit guards -
    parameter range mode (E14), the budget=0 caption (E13), the display-format
    warning that prevents a false '마트가 틀렸다' verdict (E12)."""
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "범위(range)" in text
    assert "빈 캠페인" in text
    assert "표기" in text and "값만 대조" in text
