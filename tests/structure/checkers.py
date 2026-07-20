"""Structure guards enforcing the architecture spine mechanically.

Each checker is a pure function taking the tree root to scan, so the SAME code
runs against the real repository and against synthetic violation fixtures. That
dual use is the point: at story 1-1a the repository is nearly empty, so scanning
it proves nothing. ``test_checkers_selfcheck.py`` proves the checkers bite.

Every checker returns ``(violations, scanned_file_count)``. Callers surface the
count so a rule that scanned nothing announces that fact instead of passing
quietly.

Rules enforced:
  AD-1  lane isolation (segment/churn <-> ltv), crm/common stays stateless
  AD-4  crm/config.py is the only application config file
  AD-8  pipeline stages expose main() only
  AD-9  pipelines -> crm -> config direction; campaign inner order
"""

from __future__ import annotations

import ast
from pathlib import Path

# Lane membership (AD-1). Each lane may not reference the other, and shared
# utilities may not reference either.
_LANE_A = ("crm.segment", "crm.churn")
_LANE_B = ("crm.ltv",)
_COMMON = "crm.common"

# Campaign inner order (AD-9). A module may import earlier ones, never later.
_CAMPAIGN_ORDER = ("matrix", "simulate", "sensitivity")

# Pipeline stage shape (AD-8/AD-9).
_PIPELINE_MAX_LINES = 40
_PIPELINE_ALLOWED_DEF = "main"

# Method names that mark a class as carrying fitted state (AD-1).
_FIT_METHODS = frozenset({"fit", "fit_transform", "partial_fit"})

# AD-4 bans a second APPLICATION config. Tooling manifests and generated
# tracking files are not application config and are whitelisted by exact
# relative path (kept explicit so a reader can audit the exemptions).
_CONFIG_SUFFIXES = frozenset({".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"})
_CONFIG_WHITELIST = frozenset(
    {
        "pytest.ini",  # test runner manifest
        "docs/implementation-artifacts/sprint-status.yaml",  # BMAD story tracking
    }
)
_SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"})


def _iter_python_files(root: Path, subdir: str) -> list[Path]:
    """Python files under ``root/subdir``, excluding tooling directories."""
    base = root / subdir
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if not (set(p.parts) & _SKIP_DIRS))


def _module_name(root: Path, path: Path) -> str:
    """Dotted module name for a file, e.g. crm/segment/value.py -> crm.segment.value."""
    parts = path.relative_to(root).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_parts(root: Path, path: Path) -> tuple[str, ...]:
    """Package that CONTAINS the module (used to resolve relative imports)."""
    parts = path.relative_to(root).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        return parts[:-1]
    return parts[:-1]


def _imported_modules(root: Path, path: Path) -> list[str]:
    """Absolute dotted names imported by a file.

    Relative imports are resolved against the containing package, so
    ``from ..ltv import x`` inside ``crm/churn/model.py`` is reported as
    ``crm.ltv`` - a violation cannot hide behind relative syntax.

    For ``from X import a, b`` both ``X`` and ``X.a`` / ``X.b`` are reported.
    Without the second form ``from crm import ltv`` would look like a harmless
    import of ``crm``, and ``from crm.campaign import simulate`` would look like
    an import of the package rather than of a specific stage.

    Unparseable files yield nothing rather than raising; a syntax error is the
    test suite's problem to surface, not this checker's.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    package = _package_parts(root, path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level 1 = containing package, 2 = its parent, ...
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                target = ".".join((*base, node.module)) if node.module else ".".join(base)
            else:
                target = node.module or ""
            if target:
                found.append(target)
                # `from X import a` also binds X.a - record it so a submodule
                # imported by name is visible to the lane and order rules.
                found.extend(f"{target}.{alias.name}" for alias in node.names)
    return found


def _matches(imported: str, prefix: str) -> bool:
    """True when ``imported`` is ``prefix`` itself or a submodule of it."""
    return imported == prefix or imported.startswith(prefix + ".")


def find_lane_violations(root: Path) -> tuple[list[str], int]:
    """AD-1: the BankChurners lane and the Online Retail lane never meet."""
    violations: list[str] = []
    files = _iter_python_files(root, "crm")

    for path in files:
        module = _module_name(root, path)
        if any(_matches(module, p) for p in _LANE_A):
            forbidden = _LANE_B
        elif any(_matches(module, p) for p in _LANE_B):
            forbidden = _LANE_A
        elif _matches(module, _COMMON):
            forbidden = _LANE_A + _LANE_B
        else:
            continue

        for imported in _imported_modules(root, path):
            for prefix in forbidden:
                if _matches(imported, prefix):
                    violations.append(f"AD-1 lane isolation: {module} imports {imported}")

    return violations, len(files)


def find_layering_violations(root: Path) -> tuple[list[str], int]:
    """AD-9: crm/ never imports pipelines/ (dependencies flow one way)."""
    violations: list[str] = []
    files = _iter_python_files(root, "crm")

    for path in files:
        module = _module_name(root, path)
        for imported in _imported_modules(root, path):
            if _matches(imported, "pipelines"):
                violations.append(f"AD-9 layering: {module} imports {imported}")

    return violations, len(files)


def find_campaign_order_violations(root: Path) -> tuple[list[str], int]:
    """AD-9: campaign flows matrix -> simulate -> sensitivity, never backwards."""
    violations: list[str] = []
    files = [p for p in _iter_python_files(root, "crm") if p.stem in _CAMPAIGN_ORDER and p.parent.name == "campaign"]

    for path in files:
        own_rank = _CAMPAIGN_ORDER.index(path.stem)
        for imported in _imported_modules(root, path):
            tail = imported.rsplit(".", 1)[-1]
            if tail in _CAMPAIGN_ORDER and _CAMPAIGN_ORDER.index(tail) > own_rank:
                violations.append(f"AD-9 campaign order: {path.stem} imports later stage {tail}")

    return violations, len(files)


def find_pipeline_shape_violations(root: Path) -> tuple[list[str], int]:
    """AD-8/AD-9: stages are thin - <=40 lines and no def/class besides main()."""
    violations: list[str] = []
    base = root / "pipelines"
    files = sorted(base.glob("[0-9][0-9]_*.py")) if base.exists() else []

    for path in files:
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        if line_count > _PIPELINE_MAX_LINES:
            violations.append(
                f"AD-9 pipeline shape: {path.name} has {line_count} lines (max {_PIPELINE_MAX_LINES})"
            )
        try:
            tree = ast.parse(text)
        except SyntaxError:
            violations.append(f"AD-9 pipeline shape: {path.name} does not parse")
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != _PIPELINE_ALLOWED_DEF:
                violations.append(f"AD-9 pipeline shape: {path.name} defines '{node.name}' (only main() allowed)")
            elif isinstance(node, ast.ClassDef):
                violations.append(f"AD-9 pipeline shape: {path.name} defines class '{node.name}'")

    return violations, len(files)


def find_stateful_common_violations(root: Path) -> tuple[list[str], int]:
    """AD-1: crm/common holds stateless pure functions only.

    Scope note: static analysis cannot prove statelessness in general. This
    detects the shape that actually threatens AD-1 - a class holding fitted
    state (quantile edges, scalers, encoders) that could carry one lane's
    numbers into the other. Broader mutation analysis is deliberately out of
    scope to avoid false positives.
    """
    violations: list[str] = []
    files = _iter_python_files(root, "crm/common")

    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in _FIT_METHODS:
                    violations.append(
                        f"AD-1 stateless common: {path.name} class '{node.name}' defines '{item.name}'"
                    )

    return violations, len(files)


def find_extra_config_files(root: Path) -> tuple[list[str], int]:
    """AD-4: crm/config.py is the only application configuration file."""
    violations: list[str] = []
    scanned = 0

    for path in root.rglob("*"):
        if not path.is_file() or set(path.parts) & _SKIP_DIRS:
            continue
        relative = path.relative_to(root).as_posix()
        is_config = path.suffix.lower() in _CONFIG_SUFFIXES or path.name == ".env"
        if not is_config:
            continue
        scanned += 1
        if relative in _CONFIG_WHITELIST:
            continue
        violations.append(f"AD-4 config single source: unexpected config file '{relative}'")

    return violations, scanned
