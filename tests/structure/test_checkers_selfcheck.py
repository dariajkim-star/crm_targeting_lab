"""Self-verification for the structure guards (story 1-1a, AC4).

Why this file exists
--------------------
At story 1-1a the repository is nearly empty: ``pipelines/`` has no stages and
``crm/`` holds only package stubs. Every structure guard therefore scans ZERO
relevant files and passes. A green suite would prove nothing, and stories 1-1b
through 4-4 would be built on guards nobody ever saw bite.

So each checker is exercised against a synthetic tree containing a deliberate
violation. If a checker stops detecting its violation, this file goes red even
though the real codebase is still clean.

Note the tests assert on BEHAVIOUR (does the checker flag this tree?), never by
re-implementing the checker's logic. P1 story 2-2 shipped a sign-flip bug
precisely because its test recomputed the same wrong formula and agreed with
itself.
"""

from __future__ import annotations

from pathlib import Path

from tests.structure import checkers


def _write(root: Path, relative: str, source: str) -> None:
    """Create a source file (and its package dirs) inside a synthetic tree."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _clean_tree(root: Path) -> Path:
    """A minimal tree that violates nothing."""
    _write(root, "crm/__init__.py", "")
    _write(root, "crm/config.py", "RANDOM_SEED = 42\n")
    _write(root, "crm/common/__init__.py", "")
    _write(root, "crm/common/hashing.py", "def sha(x):\n    return x\n")
    _write(root, "crm/segment/__init__.py", "")
    _write(root, "crm/segment/value.py", "from crm import config\n")
    _write(root, "crm/churn/__init__.py", "")
    _write(root, "crm/ltv/__init__.py", "")
    _write(root, "crm/campaign/__init__.py", "")
    _write(root, "crm/campaign/matrix.py", "from crm import config\n")
    _write(root, "crm/campaign/simulate.py", "from crm.campaign import matrix\n")
    _write(root, "crm/campaign/sensitivity.py", "from crm.campaign import simulate\n")
    _write(root, "pipelines/01_download.py", "def main(input_paths, output_paths):\n    return None\n")
    return root


# --- AD-1: lane isolation ----------------------------------------------------


def test_lane_checker_flags_segment_importing_ltv(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/segment/value.py", "from crm.ltv import expected_ltv\n")

    violations, scanned = checkers.find_lane_violations(root)

    assert scanned > 0
    assert any("segment" in v and "ltv" in v for v in violations)


def test_lane_checker_flags_ltv_importing_churn(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/ltv/demo.py", "import crm.churn.model\n")

    violations, _ = checkers.find_lane_violations(root)

    assert any("ltv" in v and "churn" in v for v in violations)


def test_lane_checker_flags_relative_import_across_lanes(tmp_path: Path) -> None:
    """A relative import is the same violation wearing a disguise."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/churn/model.py", "from ..ltv import expected_ltv\n")

    violations, _ = checkers.find_lane_violations(root)

    assert any("churn" in v and "ltv" in v for v in violations)


def test_lane_checker_flags_common_importing_a_lane(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/common/hashing.py", "from crm.segment import value\n")

    violations, _ = checkers.find_lane_violations(root)

    assert violations


def test_lane_checker_passes_clean_tree(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)

    violations, scanned = checkers.find_lane_violations(root)

    assert violations == []
    assert scanned > 0


# --- AD-9: layering direction ------------------------------------------------


def test_layering_checker_flags_crm_importing_pipelines(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/segment/value.py", "from pipelines import main\n")

    violations, scanned = checkers.find_layering_violations(root)

    assert scanned > 0
    assert any("pipelines" in v for v in violations)


def test_layering_checker_passes_clean_tree(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)

    violations, _ = checkers.find_layering_violations(root)

    assert violations == []


# --- AD-9: campaign inner order (matrix -> simulate -> sensitivity) ----------


def test_campaign_checker_flags_matrix_importing_simulate(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/matrix.py", "from crm.campaign import simulate\n")

    violations, scanned = checkers.find_campaign_order_violations(root)

    assert scanned > 0
    assert any("matrix" in v and "simulate" in v for v in violations)


def test_campaign_checker_flags_simulate_importing_sensitivity(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/simulate.py", "from crm.campaign import sensitivity\n")

    violations, _ = checkers.find_campaign_order_violations(root)

    assert violations


def test_campaign_checker_allows_forward_direction(tmp_path: Path) -> None:
    """sensitivity may import simulate; that is the permitted direction."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/sensitivity.py", "from crm.campaign import simulate, matrix\n")

    violations, _ = checkers.find_campaign_order_violations(root)

    assert violations == []


# --- AD-8 / AD-9: pipeline stage shape --------------------------------------


def test_pipeline_checker_flags_file_over_forty_lines(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    body = "\n".join(f"# filler line {i}" for i in range(50))
    _write(root, "pipelines/02_features.py", f"def main(input_paths, output_paths):\n    return None\n{body}\n")

    violations, scanned = checkers.find_pipeline_shape_violations(root)

    assert scanned > 0
    assert any("40" in v or "lines" in v for v in violations)


def test_pipeline_checker_flags_helper_def(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(
        root,
        "pipelines/03_train_churn.py",
        "def helper():\n    return 1\n\n\ndef main(input_paths, output_paths):\n    return helper()\n",
    )

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("helper" in v for v in violations)


def test_pipeline_checker_flags_module_level_class(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/04_ltv_demo.py", "class Runner:\n    pass\n\n\ndef main(i, o):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("Runner" in v for v in violations)


def test_pipeline_checker_passes_conforming_stage(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)

    violations, scanned = checkers.find_pipeline_shape_violations(root)

    assert violations == []
    assert scanned > 0


# --- AD-1: crm/common must stay stateless ------------------------------------


def test_common_checker_flags_class_with_fit(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/common/scaler.py",
        "class Scaler:\n    def fit(self, df):\n        self.mean_ = df.mean()\n        return self\n",
    )

    violations, scanned = checkers.find_stateful_common_violations(root)

    assert scanned > 0
    assert any("Scaler" in v for v in violations)


def test_common_checker_flags_fit_transform(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/common/enc.py", "class Enc:\n    def fit_transform(self, df):\n        return df\n")

    violations, _ = checkers.find_stateful_common_violations(root)

    assert violations


def test_common_checker_passes_pure_functions(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)

    violations, scanned = checkers.find_stateful_common_violations(root)

    assert violations == []
    assert scanned > 0


# --- AD-4: config single source ----------------------------------------------


def test_config_checker_flags_extra_yaml(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/settings.yaml", "rate: 0.3\n")

    violations, _ = checkers.find_extra_config_files(root)

    assert any("settings.yaml" in v for v in violations)


def test_config_checker_flags_dotenv(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, ".env", "SECRET=1\n")

    violations, _ = checkers.find_extra_config_files(root)

    assert violations


def test_config_checker_allows_whitelisted_tooling_files(tmp_path: Path) -> None:
    """AD-4 bans a second APPLICATION config, not tooling manifests."""
    root = _clean_tree(tmp_path)
    _write(root, "pytest.ini", "[pytest]\n")
    _write(root, "docs/implementation-artifacts/sprint-status.yaml", "development_status: {}\n")

    violations, _ = checkers.find_extra_config_files(root)

    assert violations == []
