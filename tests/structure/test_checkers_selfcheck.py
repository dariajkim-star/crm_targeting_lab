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


def test_lane_checker_flags_submodule_via_parent_package(tmp_path: Path) -> None:
    """Regression: `from crm import ltv` is the exact form the initial checker
    missed - it recorded only the module `crm`, so binding the lane package by
    name slipped through. Keep this fixture forever."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/segment/value.py", "from crm import ltv\n")

    violations, _ = checkers.find_lane_violations(root)

    assert any("segment" in v and "ltv" in v for v in violations)


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


def test_campaign_checker_ignores_external_name_collisions(tmp_path: Path) -> None:
    """`import scipy.sensitivity` shares only a tail name with a stage.

    Regression: the original tail-only comparison flagged ANY imported name
    ending in a stage word, rejecting legitimate third-party imports."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/matrix.py", "import scipy.sensitivity\nfrom anylib import simulate\n")

    violations, _ = checkers.find_campaign_order_violations(root)

    assert violations == []


# --- AD-12: priority.py must not compute its own quadrant cut ----------------


def test_selfcut_checker_flags_quantile_in_priority(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/priority.py",
        "def cut(s):\n    return s.quantile(0.5)\n",
    )

    violations, scanned = checkers.find_priority_selfcut_violations(root)

    assert scanned == 1
    assert any("quantile" in v for v in violations)


def test_selfcut_checker_flags_numpy_percentile(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/priority.py",
        "import numpy as np\ndef cut(a):\n    return np.percentile(a, 50)\n",
    )

    violations, _ = checkers.find_priority_selfcut_violations(root)

    assert any("percentile" in v for v in violations)


def test_selfcut_checker_allows_consuming_priority(tmp_path: Path) -> None:
    """Consuming quadrant labels and ranking is the permitted shape."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/priority.py",
        "import numpy as np\ndef rank(s):\n    return np.lexsort((s.to_numpy(),))\n",
    )

    violations, scanned = checkers.find_priority_selfcut_violations(root)

    assert scanned == 1
    assert violations == []


def test_selfcut_checker_fails_closed_on_syntax_error(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/priority.py", "def broken(:\n")

    violations, scanned = checkers.find_priority_selfcut_violations(root)

    assert scanned == 0
    assert violations


# --- AD-8 / AD-9: pipeline stage shape --------------------------------------


def test_pipeline_checker_flags_file_over_forty_lines(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    body = "\n".join(f"# filler line {i}" for i in range(50))
    _write(root, "pipelines/02_features.py", f"def main(input_paths, output_paths):\n    return None\n{body}\n")

    violations, scanned = checkers.find_pipeline_shape_violations(root)

    assert scanned > 0
    # Pin the specific message: a loose match ("40" anywhere) could be satisfied
    # by an unrelated violation and keep this test green through a regression.
    assert any("02_features.py has 52 lines (max 40)" in v for v in violations)


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


def test_pipeline_checker_flags_nonconforming_filename(tmp_path: Path) -> None:
    """A stage that dodges NN_<verb>.py naming must be a violation, not exempt.

    Regression for a High finding: the original glob scanned only matching
    names, so `pipelines/download.py` bypassed every shape rule AND vanished
    from the scanned count that the coverage report trusts."""
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/download.py", "def main(i, o):\n    return None\n")

    violations, scanned = checkers.find_pipeline_shape_violations(root)

    assert any("download.py" in v and "naming" in v for v in violations)
    assert scanned == 2  # conforming 01_download.py AND the dodger both counted


def test_pipeline_checker_flags_nested_subdirectory_file(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/etl/01_hidden.py", "def main(i, o):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("etl/01_hidden.py" in v for v in violations)


def test_pipeline_checker_flags_def_nested_inside_main(tmp_path: Path) -> None:
    """A helper hidden INSIDE main() is the same rule dodged one indent deeper."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "pipelines/05_marts.py",
        "def main(input_paths, output_paths):\n    def helper():\n        return 1\n    return helper()\n",
    )

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("helper" in v for v in violations)


def test_pipeline_checker_reports_non_utf8_instead_of_crashing(tmp_path: Path) -> None:
    """A cp949-encoded stage must yield a violation, not an unhandled exception."""
    root = _clean_tree(tmp_path)
    path = root / "pipelines" / "02_features.py"
    path.write_bytes("def main(i, o):\n    return None  # 한글주석\n".encode("cp949"))

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("not valid UTF-8" in v for v in violations)


def test_pipeline_checker_flags_missing_main(tmp_path: Path) -> None:
    """AD-8: a stage IS its main(); a file without one is not a stage."""
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/06_report.py", "RESULT = 1\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("06_report.py" in v and "main" in v for v in violations)


def test_pipeline_checker_flags_wrong_main_signature(tmp_path: Path) -> None:
    """AD-8 fixes the signature as main(input_paths, output_paths) - exactly."""
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/07_wrong.py", "def main(src, dst):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("07_wrong.py" in v and "input_paths" in v for v in violations)


def test_pipeline_checker_flags_nested_main_redefinition(tmp_path: Path) -> None:
    """Naming a nested helper `main` satisfied only-main AND hijacked the
    signature check - one identifier defeating two rules at once."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "pipelines/08_nested.py",
        "def main(input_paths, output_paths):\n    def main(x):\n        return x\n    return main(1)\n",
    )

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("08_nested.py" in v and "nested" in v for v in violations)


def test_pipeline_checker_flags_async_main(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/09_async.py", "async def main(input_paths, output_paths):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("09_async.py" in v and "async" in v for v in violations)


def test_pipeline_checker_flags_extra_main_parameters(tmp_path: Path) -> None:
    """*args/**kwargs/kw-only/defaults change the call contract - all rejected."""
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/10_extra.py", "def main(input_paths, output_paths, *, debug=True):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("10_extra.py" in v and "input_paths" in v for v in violations)


def test_pipeline_checker_accepts_positional_only_main(tmp_path: Path) -> None:
    """`/` keeps the positional call contract identical - not a violation."""
    root = _clean_tree(tmp_path)
    _write(root, "pipelines/11_posonly.py", "def main(input_paths, output_paths, /):\n    return None\n")

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert not any("11_posonly.py" in v for v in violations)


def test_pipeline_checker_flags_lambda(tmp_path: Path) -> None:
    root = _clean_tree(tmp_path)
    _write(
        root,
        "pipelines/12_lambda.py",
        "SORT = lambda x: x\n\n\ndef main(input_paths, output_paths):\n    return SORT(1)\n",
    )

    violations, _ = checkers.find_pipeline_shape_violations(root)

    assert any("12_lambda.py" in v and "lambda" in v for v in violations)


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


def test_config_checker_ignores_data_artifacts(tmp_path: Path) -> None:
    """A pipeline output is not configuration (regression guard).

    Story 1-1b writes ``data/meta.json`` and epic 4 writes mart JSON. Scanning
    by suffix alone reported those as "unexpected config file", which would have
    turned this guard red the moment real data landed - and pointed the reader
    at the wrong problem. Filenames under these trees are machine-chosen, so the
    exclusion is by directory, not by a per-file whitelist.
    """
    root = _clean_tree(tmp_path)
    _write(root, "data/meta.json", '{"rows": 10127}\n')
    _write(root, "marts/segment_profile.json", '{"segments": 4}\n')
    _write(root, "models/churn_xgb.json", '{"booster": "gbtree"}\n')

    violations, _ = checkers.find_extra_config_files(root)

    assert violations == []


def test_config_checker_still_flags_config_outside_data_dirs(tmp_path: Path) -> None:
    """The data-dir exclusion must not blunt the rule everywhere else."""
    root = _clean_tree(tmp_path)
    _write(root, "data/meta.json", '{"rows": 1}\n')
    _write(root, "crm/settings.json", '{"retention_rate": 0.3}\n')

    violations, _ = checkers.find_extra_config_files(root)

    assert any("crm/settings.json" in v for v in violations)
    assert not any("meta.json" in v for v in violations)


def test_config_checker_flags_dotenv_variants(tmp_path: Path) -> None:
    """dotenv tooling loads `.env.local` as eagerly as `.env`; NTFS ignores case."""
    root = _clean_tree(tmp_path)
    _write(root, ".env.local", "SECRET=1\n")
    _write(root, ".ENV", "SECRET=2\n")

    violations, _ = checkers.find_extra_config_files(root)

    assert any(".env.local" in v for v in violations)
    assert any(".ENV" in v for v in violations)


def test_config_checker_ignores_tooling_dirs(tmp_path: Path) -> None:
    """Tool-generated JSON (.claude etc.) is not application config."""
    root = _clean_tree(tmp_path)
    _write(root, ".claude/settings.local.json", '{"permissions": []}\n')
    _write(root, ".vscode/settings.json", '{"editor.rulers": [100]}\n')

    violations, _ = checkers.find_extra_config_files(root)

    assert violations == []


def test_skip_dirs_match_relative_parts_not_absolute(tmp_path: Path) -> None:
    """A repo checked out UNDER a dir named like a skip dir must still be scanned.

    Regression: matching on absolute path parts made e.g. any checkout under a
    `node_modules`-named ancestor scan zero files and pass every rule silently."""
    root = _clean_tree(tmp_path / "node_modules" / "repo")
    _write(root, "crm/segment/value.py", "from crm.ltv import x\n")

    violations, scanned = checkers.find_lane_violations(root)

    assert scanned > 0
    assert violations


# --- AD-4: config guard failure path (the guard must bite, automatically) -----


def test_config_grid_guard_raises_on_out_of_grid_value() -> None:
    """Prove the import-time guard fails when the representative value drifts.

    Executes the REAL crm/config.py source with one value patched out of its
    grid - not a reimplementation of the check. If someone deletes or weakens
    the guard, this test goes red. (Guard uses `raise`, not `assert`, so
    `python -O` cannot strip it.)"""
    source = (Path(checkers.__file__).parents[2] / "crm" / "config.py").read_text(encoding="utf-8")
    assert "RETENTION_SUCCESS_RATE: float = 0.30" in source  # patch anchor must exist
    broken = source.replace("RETENTION_SUCCESS_RATE: float = 0.30", "RETENTION_SUCCESS_RATE: float = 0.33")

    try:
        exec(compile(broken, "<patched-config>", "exec"), {"__name__": "crm.config_patched", "__file__": str(Path(checkers.__file__).parents[2] / "crm" / "config.py")})
    except ValueError as err:
        assert "AD-4" in str(err)
    else:
        raise AssertionError("out-of-grid RETENTION_SUCCESS_RATE must fail at import time")


def test_config_grid_guard_passes_on_shipped_values() -> None:
    """The shipped config imports cleanly (sanity companion to the red path)."""
    import importlib

    import crm.config

    importlib.reload(crm.config)


# --- AD-11: single value definition ------------------------------------------


def test_value_guard_flags_subscript_recomputation(tmp_path: Path) -> None:
    """The realistic breach: a consumer indexes the column directly."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        "def value(df):\n    return df['Total_Trans_Amt'] * 0.02\n",
    )

    violations, scanned = checkers.find_value_recomputation_violations(root)

    assert scanned > 0
    assert any("matrix" in v for v in violations)


def test_value_guard_flags_attribute_access(tmp_path: Path) -> None:
    """``df.Total_Trans_Amt`` is the same breach in the other spelling."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/churn/model.py", "def f(df):\n    return df.Total_Trans_Amt\n")

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("churn.model" in v for v in violations)


def test_value_guard_exempts_the_definition_module(tmp_path: Path) -> None:
    """value.py is the ONE module allowed to name the column.

    Without this the guard would flag its own definition and the rule would be
    unimplementable.
    """
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/segment/value.py",
        "def customer_value(df):\n    return df['Total_Trans_Amt'].astype(float)\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert violations == []


def test_value_guard_ignores_mentions_in_prose(tmp_path: Path) -> None:
    """A module explaining the rule is not breaking it.

    This is the false positive a text grep would produce, and the reason the
    checker is AST-based.
    """
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        '"""Consumes customer_value(); never reads Total_Trans_Amt itself."""\n'
        "# Total_Trans_Amt must not be referenced here.\n"
        "def value(df):\n    return df\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert violations == []


def test_value_guard_allows_consuming_the_definition(tmp_path: Path) -> None:
    """The SANCTIONED pattern must stay green, or the guard blocks correct code."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        "from crm.segment.value import customer_value\n"
        "def quadrant(df):\n    return customer_value(df) > 3899.0\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert violations == []


def test_value_guard_flags_imported_value_column_alias(tmp_path: Path) -> None:
    """Importing the column NAME is a bypass, not a workaround.

    Verified to slip through the literal-only check: no string constant and no
    attribute access appears in the consuming module at all.
    """
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        "from crm.segment.value import VALUE_COLUMN\n"
        "def v(df):\n    return df[VALUE_COLUMN] * 0.02\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("matrix" in v for v in violations)


def test_value_guard_flags_private_value_column_import(tmp_path: Path) -> None:
    """The underscore spelling must be blocked too - a leading _ stops nobody."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        "from crm.segment.value import _VALUE_COLUMN\n"
        "def v(df):\n    return df[_VALUE_COLUMN]\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("matrix" in v for v in violations)


def test_value_guard_flags_module_alias_attribute_access(tmp_path: Path) -> None:
    """Reaching the name through the module object is the same escape."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/churn/model.py",
        "import crm.segment.value as value_definition\n"
        "def v(df):\n    return df[value_definition.VALUE_COLUMN]\n",
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("churn.model" in v for v in violations)


def test_value_guard_flags_dataframe_eval_expression(tmp_path: Path) -> None:
    """pandas' own expression API hides the column inside a larger string."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        'def v(df):\n    return df.eval("Total_Trans_Amt * 0.02")\n',
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("matrix" in v for v in violations)


def test_value_guard_flags_dataframe_query_expression(tmp_path: Path) -> None:
    """query() is the same hole as eval()."""
    root = _clean_tree(tmp_path)
    _write(
        root,
        "crm/campaign/matrix.py",
        'def v(df):\n    return df.query("Total_Trans_Amt > 3899")\n',
    )

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("matrix" in v for v in violations)


def test_value_guard_fails_closed_on_unparseable_file(tmp_path: Path) -> None:
    """A file the rule could not read must NOT pass quietly.

    Skipping it would let a syntax error hide a breach while still counting the
    file as scanned - the guard would report coverage it never had.
    """
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/matrix.py", 'def v(df):\n    return df["Total_Trans_Amt" * 0.02\n')

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("matrix" in v for v in violations)


def test_value_guard_scanned_count_excludes_unreadable_and_exempt_files(tmp_path: Path) -> None:
    """`scanned` means files actually PARSED, so coverage is never overstated."""
    root = _clean_tree(tmp_path)
    _, baseline = checkers.find_value_recomputation_violations(root)
    _write(root, "crm/campaign/broken.py", "def v(:\n")

    _, scanned = checkers.find_value_recomputation_violations(root)

    assert scanned == baseline, "an unparseable file must not be counted as scanned"


def test_value_guard_scans_modules_in_nested_packages(tmp_path: Path) -> None:
    """A consumer buried deeper in the tree is still in scope."""
    root = _clean_tree(tmp_path)
    _write(root, "crm/campaign/deep/__init__.py", "")
    _write(root, "crm/campaign/deep/nested.py", "def v(df):\n    return df.Total_Trans_Amt\n")

    violations, _ = checkers.find_value_recomputation_violations(root)

    assert any("nested" in v for v in violations)
