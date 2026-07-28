"""Public-release contract: the repo stays publishable (story 4-4, AD-10/NFR7).

Three surfaces are pinned:

  - the TREE never tracks a data/model artifact (the commit-HISTORY scan is a
    one-time audit recorded in the story - history is immutable, so what a
    regression guard must catch is a FUTURE artifact slipping in, and that is
    a property of the current tree),
  - the README's headline numbers are the SAME strings as the mart goldens -
    a retrain that moves the mart must move the README in the same change, or
    the portfolio front page quotes numbers the artifact no longer produces,
  - the publish runbook keeps its verification step - a runbook without the
    anchor-check step ships a workbook nobody compared against the mart.

Slicing discipline inherited from 4-3: every scoped assert names its anchors.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
RUNBOOK = REPO_ROOT / "docs" / "tableau-publish-runbook.md"

# Binary data/model artifact suffixes that must never be tracked. The mart CSV
# is the deliberate exception (AD-2: marts/ is the committed contract surface).
_BANNED_SUFFIXES = (".parquet", ".joblib", ".pkl")


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=REPO_ROOT, timeout=30
    )
    assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
    return result.stdout.splitlines()


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _readme_section(heading: str) -> str:
    text = _readme_text()
    match = re.search(rf"^## {re.escape(heading)}", text, flags=re.MULTILINE)
    assert match, f"README lost its '{heading}' section"
    end = text.find("\n## ", match.start() + 1)
    return text[match.start():end] if end != -1 else text[match.start():]


# --- AC1: no data/model artifact is ever tracked -----------------------------


def test_no_data_or_model_artifact_is_tracked() -> None:
    """AD-10/NFR7: `data/` and `models/` are gitignored, but an ignore file
    only advises - `git add -f` or a moved file bypasses it silently. The
    tracked-file list is the fact the ignore file merely intends."""
    offenders = [
        path for path in _tracked_files()
        if path.lower().endswith(_BANNED_SUFFIXES)
    ]

    assert offenders == [], f"tracked data/model artifacts: {offenders}"


def test_the_only_tracked_csv_data_is_the_mart() -> None:
    """CSV needs a narrower rule: tooling manifests (.claude/_bmad) are fine,
    and the mart is the deliberate AD-2 exception - but a stray data export
    anywhere else would publish rows nobody audited."""
    csvs = [
        path for path in _tracked_files()
        if path.lower().endswith(".csv")
        and not path.startswith((".claude/", "_bmad/"))
    ]

    assert csvs == ["marts/mart_customers.csv"], f"unexpected tracked CSVs: {csvs}"


# --- AC2/AC4: README headline numbers == mart goldens ------------------------


def test_readme_headline_numbers_match_the_mart_goldens() -> None:
    """The same dual-update contract the schema doc and the dashboard spec
    carry - the README is the third copy of these numbers, and the portfolio
    front page is the worst possible place for a stale one."""
    section = _readme_section("핵심 수치")

    assert "10,127" in section
    assert "1,454,088" in section
    assert "0.132753" in section
    assert "3,899" in section
    for labelled in ("save_first 443", "watch 2,089", "low_cost_keep 4,624", "accept_churn 2,971"):
        assert labelled in section, f"README lost the labelled count '{labelled}'"
    assert "0.9508" in section  # PR-AUC, from the committed model meta


def test_readme_states_all_four_assumptions() -> None:
    """성공신호 ④: every assumption named, none implied."""
    section = _readme_section("한계와 가정")

    assert "결합 불가" in section  # AD-1: the two datasets never join
    assert "단면" in section  # Attrition_Flag is a snapshot label
    assert "정책가정" in section  # 0.30 rate / 5.0 cost are assumed
    assert "GBP" in section  # currency: unitless customer lane, GBP LTV lane


def test_readme_admits_what_was_not_done() -> None:
    """정직성: the freeze and the not-yet-published link are stated, not
    hidden - a portfolio that hides its cuts invites the reader to find them."""
    text = _readme_text()

    assert "동결" in text  # epic-2 / LTV demo not performed
    assert "테스트 수는 실행 환경" in text or "환경 기준" in text  # D2


# --- AC3/AC4: the runbook keeps its verification step ------------------------


def test_runbook_exists_with_account_and_anchor_steps() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Tableau Public 계정" in text  # step 0 - OQ-5
    assert "검산 앵커" in text  # the workbook-vs-mart comparison step
    assert "공개 조회 가능" in text  # the publish disclosure
    assert "dashboard-spec.md" in text  # the spec is the build source
