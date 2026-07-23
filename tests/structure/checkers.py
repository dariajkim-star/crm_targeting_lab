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
  AD-11 customer value is defined once, in crm/segment/value.py
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
_CAMPAIGN_ORDER = ("matrix", "simulate", "priority", "sensitivity")

# AD-12: quadrant cuts are owned by matrix.py alone. priority.py CONSUMES
# `quadrant_official`; it must never compute a cut of its own. The mechanical
# signature of a self-cut is a threshold-forming call - `.quantile(...)`,
# `.percentile(...)`, `.median(...)` - so priority.py carrying any of these is a
# re-cut regardless of intent. Story 3-3 AC3 was otherwise verified only by
# prose and an uncommitted script (story 3-3 code review).
_SELFCUT_MODULE = "crm/campaign/priority.py"
_SELFCUT_METHODS = frozenset({"quantile", "percentile", "median"})

# AD-12, symmetric guard for story 3-4. sensitivity.py CONSUMES the official
# quadrant column (and, in its risk_quantile annex, `assign_quadrant` with a
# replaced rule); it must never cut a quantile of its own. AD-12 names the
# simulator and the sensitivity sweep explicitly, yet only priority.py was
# mechanically guarded (story 3-3 code review). The self-cut signature is the
# same threshold-forming call. This guard co-exists with the risk_quantile
# sweep (D2): the sweep hands the quantile LEVEL to `matrix.assign_quadrant`,
# which owns the `.quantile` call, so sensitivity.py itself carries none.
_SENSITIVITY_SELFCUT_MODULE = "crm/campaign/sensitivity.py"

# Pipeline stage shape (AD-8/AD-9).
_PIPELINE_MAX_LINES = 40
_PIPELINE_ALLOWED_DEF = "main"

# AD-11: the value proxy column, and the ONE module allowed to name it.
# Any other module under crm/ referencing it is recomputing customer value.
_VALUE_COLUMN = "Total_Trans_Amt"
_VALUE_DEFINITION_MODULE = "crm/segment/value.py"
_VALUE_DEFINITION_DOTTED = "crm.segment.value"
# Names under which value.py could hand the column string to a caller. Importing
# one of these, or reaching it through the module object, bypasses both the
# string-literal and the attribute check - so both spellings are named here.
_VALUE_COLUMN_ALIASES = frozenset({"VALUE_COLUMN", "_VALUE_COLUMN"})
# pandas expression APIs that take the column name inside a larger string.
_EXPRESSION_METHODS = frozenset({"eval", "query"})

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
# Data-artifact trees are OUT OF SCOPE for AD-4, by directory rather than by
# filename. AD-4 constrains where configuration lives, not which file
# extensions may exist: story 1-1b writes `data/meta.json` (freshness metadata)
# and epic 4 writes mart JSON. Scanning those by suffix would report a data
# artifact as "unexpected config file" - a guard firing on the wrong thing is
# worse than no guard, because the message misleads whoever debugs it.
# Directory-level exclusion (not a per-file whitelist) is deliberate: these
# trees are machine-written and their filenames are not knowable in advance.
_DATA_DIRS = frozenset({"data", "marts", "models"})
# Tooling trees: never application code or config. `.claude` / `.playwright-mcp`
# / `_bmad` / editor dirs can appear at any time without a commit, so excluding
# them keeps the AD-4 scan from flagging tool-owned TOML/JSON as a second config
# file. `_bmad` is the BMAD story-workflow install (its own config.toml and
# per-skill custom/*.toml live under it); it is project tooling, not application
# configuration, the same category as `.claude`.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        ".claude",
        ".playwright-mcp",
        "_bmad",
        ".vscode",
        ".idea",
    }
)


def _is_skipped(root: Path, path: Path) -> bool:
    """Skip-dir check against ROOT-RELATIVE parts only.

    Matching on absolute ``path.parts`` would let the repository's location
    poison every rule - a checkout under ``C:/tools/node_modules/repo`` would
    scan zero files and pass silently.
    """
    return bool(set(path.relative_to(root).parts) & _SKIP_DIRS)


def _iter_python_files(root: Path, subdir: str) -> list[Path]:
    """Python files under ``root/subdir``, excluding tooling directories."""
    base = root / subdir
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.py") if not _is_skipped(root, p))


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
                if node.level - 1 > len(package):
                    # Deeper than the tree itself: a runtime ImportError, not a
                    # resolvable module. Skip rather than slice with a negative
                    # index and fabricate a wrong base package.
                    continue
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
            # Only names inside crm.campaign are stages. Without this prefix
            # check `import scipy.sensitivity` would be flagged as an order
            # violation purely because its tail collides with a stage name.
            if not _matches(imported, "crm.campaign"):
                continue
            tail = imported.rsplit(".", 1)[-1]
            if tail in _CAMPAIGN_ORDER and _CAMPAIGN_ORDER.index(tail) > own_rank:
                violations.append(f"AD-9 campaign order: {path.stem} imports later stage {tail}")

    return violations, len(files)


def _find_selfcut_violations(root: Path, module_rel: str, label: str, mandate: str) -> tuple[list[str], int]:
    """Scan one campaign module for a threshold-forming call (AD-12).

    Shared by the priority (3-3) and sensitivity (3-4) guards: both consume
    ``quadrant_official`` and neither may cut a quantile of its own, so the
    mechanical check - a call to ``.quantile``/``.percentile``/``.median`` on any
    object - is identical. ``label`` and ``mandate`` only shape the message so a
    failure names the right module and rule.

    Fail-closed: an unparseable module is a violation, not a skip.
    """
    violations: list[str] = []
    target = root / module_rel
    if not target.exists():
        # Not yet written - report zero scanned so the coverage table shows the
        # rule inspected nothing rather than passing quietly.
        return violations, 0

    module = _module_name(root, target)
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except SyntaxError as err:
        return [
            f"AD-12 {label} self-cut: {module} could not be scanned "
            f"(syntax error at line {err.lineno}) - the rule fails closed"
        ], 0
    except UnicodeDecodeError:
        return [f"AD-12 {label} self-cut: {target.name} is not valid UTF-8"], 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # `series.quantile(...)` / `np.percentile(...)` - both are attribute
        # accesses whose final name is the threshold-forming method.
        if isinstance(func, ast.Attribute) and func.attr in _SELFCUT_METHODS:
            violations.append(
                f"AD-12 {label} self-cut: {module} calls .{func.attr}() - {mandate}"
            )

    return violations, 1


def find_priority_selfcut_violations(root: Path) -> tuple[list[str], int]:
    """AD-12: priority.py consumes quadrant_official, never cuts its own.

    Story 3-3 AC3 requires the priority module to consume the official quadrant
    column rather than compute a threshold of its own. Nothing mechanical
    enforced that - the AD-9 order guard actually PERMITS priority.py to import
    matrix.py, and the only positive evidence for AC3 was report prose plus an
    uncommitted script (story 3-3 code review). This scans for the signature of
    a self-cut: a call to ``.quantile``/``.percentile``/``.median`` on any
    object, or the numpy equivalents, inside priority.py.

    Fail-closed: an unparseable module is a violation, not a skip.
    """
    return _find_selfcut_violations(
        root,
        _SELFCUT_MODULE,
        "priority",
        "priority.py must consume quadrant_official, not compute a cut",
    )


def find_sensitivity_selfcut_violations(root: Path) -> tuple[list[str], int]:
    """AD-12: sensitivity.py consumes quadrant_official, never cuts its own.

    The symmetric partner to :func:`find_priority_selfcut_violations` for story
    3-4. AD-12 names the sensitivity sweep explicitly, but only priority.py was
    mechanically guarded. The risk_quantile annex (D2) is designed to stay clear
    of this: it hands the quantile LEVEL to ``matrix.assign_quadrant``, which
    owns the ``.quantile`` call, so sensitivity.py itself computes no cut.

    Fail-closed: an unparseable module is a violation, not a skip.
    """
    return _find_selfcut_violations(
        root,
        _SENSITIVITY_SELFCUT_MODULE,
        "sensitivity",
        "sensitivity.py must consume assign_quadrant, not compute a cut",
    )


def _stage_name_pattern_ok(name: str) -> bool:
    """True for the canonical stage filename shape ``NN_<verb>.py``."""
    return len(name) > 3 and name[:2].isdigit() and name[2] == "_" and name.endswith(".py")


def find_pipeline_shape_violations(root: Path) -> tuple[list[str], int]:
    """AD-8/AD-9: stages are thin - <=40 lines and no def/class besides main().

    EVERY ``.py`` under ``pipelines/`` (recursively) is in scope. A file that
    dodges the ``NN_<verb>.py`` naming or hides in a subdirectory is itself a
    violation - otherwise renaming a stage would silently exempt it from the
    40-line and main-only rules, and it would not even appear in the scanned
    count that the coverage report relies on.
    """
    violations: list[str] = []
    base = root / "pipelines"
    files = sorted(p for p in base.rglob("*.py") if not _is_skipped(root, p)) if base.exists() else []

    for path in files:
        if path.parent != base or not _stage_name_pattern_ok(path.name):
            rel = path.relative_to(base).as_posix()
            violations.append(
                f"AD-9 pipeline shape: '{rel}' does not match the NN_<verb>.py stage naming "
                f"at pipelines/ top level - shape rules cannot be dodged by renaming"
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"AD-9 pipeline shape: {path.name} is not valid UTF-8")
            continue
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
        # Walk the WHOLE tree: a def/class/lambda nested inside main() is the
        # same rule dodged one indent deeper.
        top_level = {id(node) for node in tree.body}
        main_defs: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name != _PIPELINE_ALLOWED_DEF:
                    violations.append(
                        f"AD-9 pipeline shape: {path.name} defines '{node.name}' (only main() allowed)"
                    )
                elif id(node) not in top_level:
                    # Naming a nested helper `main` used to satisfy the
                    # only-main rule AND hijack the signature check.
                    violations.append(
                        f"AD-9 pipeline shape: {path.name} defines a nested 'main' "
                        f"(only the module-level main() is allowed)"
                    )
                else:
                    main_defs.append(node)
            elif isinstance(node, ast.ClassDef):
                violations.append(f"AD-9 pipeline shape: {path.name} defines class '{node.name}'")
            elif isinstance(node, ast.Lambda):
                violations.append(f"AD-9 pipeline shape: {path.name} defines a lambda (only main() allowed)")

        # AD-8: a stage IS its main(input_paths, output_paths) - exactly that
        # signature, so every stage is invocable the same way.
        if not main_defs:
            violations.append(f"AD-8 pipeline shape: {path.name} has no main() - a stage IS its main()")
            continue

        main_def = main_defs[0]
        if isinstance(main_def, ast.AsyncFunctionDef):
            violations.append(f"AD-8 pipeline shape: {path.name} main() is async - stages are called synchronously")

        args = main_def.args
        # positional-only is fine (same positional call), but extras are not:
        # *args/**kwargs/keyword-only/defaults all change the call contract.
        arg_names = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args]
        extras = args.vararg or args.kwarg or args.kwonlyargs or args.defaults or args.kw_defaults
        if arg_names != ["input_paths", "output_paths"] or extras:
            violations.append(
                f"AD-8 pipeline shape: {path.name} main({', '.join(arg_names)}"
                f"{', ...' if extras else ''}) - required signature is "
                f"main(input_paths, output_paths)"
            )

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
        except UnicodeDecodeError:
            violations.append(f"AD-1 stateless common: {path.name} is not valid UTF-8")
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


def find_value_recomputation_violations(root: Path) -> tuple[list[str], int]:
    """AD-11: only crm/segment/value.py may name the customer-value column.

    Every other module consumes ``customer_value(df)``. The moment 3-1, 3-2,
    3-3 and 4-1 each reach for ``Total_Trans_Amt`` directly, the same customer
    can carry four different values and nothing in the test suite notices -
    which is the exact scenario AD-11 exists to prevent.

    Detection is AST-based and covers four routes to the column, all of which
    were verified to slip past a naive literal-only check:

        df["Total_Trans_Amt"]          ->  ast.Constant (a string literal)
        df.Total_Trans_Amt             ->  ast.Attribute
        from ...value import VALUE_COLUMN; df[VALUE_COLUMN]
                                       ->  ast.ImportFrom of the column alias
        import ...value as v; df[v.VALUE_COLUMN]
                                       ->  ast.Attribute on the alias name
        df.eval("Total_Trans_Amt * w") ->  string ARGUMENT of eval/query

    The last three are not contrived bypasses. The import route is the obvious
    thing a consumer would write once value.py exports the name, and
    ``eval``/``query`` are pandas' own column-expression APIs - both reported
    zero violations before this was added.

    A whole-file text grep would be simpler and wrong: it also matches the name
    inside comments and docstrings, so a module that merely EXPLAINS the rule
    would be reported as breaking it. A guard that fires on prose trains people
    to ignore it. Substring matching is therefore confined to the string
    arguments of ``eval``/``query``, where a bare mention cannot occur.

    Scope note: this rule still does not chase constructed strings. A module
    binding ``col = "Total_Trans_" + "Amt"`` defeats it. Static analysis cannot
    close that hole in general, and the rule targets realistic reaches for the
    column, not a determined bypass.

    Fail-closed: a file that cannot be parsed is reported as a violation rather
    than skipped. Silently skipping it would let an unparseable module hide a
    breach AND inflate the scanned count with a file nothing inspected.
    """
    violations: list[str] = []
    # The exempt module is excluded from the SCANNED count as well as from the
    # rule: reporting it as scanned would overstate the coverage report by the
    # one file the rule deliberately never inspects.
    files = [
        p for p in _iter_python_files(root, "crm")
        if p.relative_to(root).as_posix() != _VALUE_DEFINITION_MODULE
    ]
    # Counts files actually PARSED, so the coverage report never credits a file
    # the rule failed to read.
    scanned = 0

    for path in files:
        module = _module_name(root, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as err:
            violations.append(
                f"AD-11 single value definition: {module} could not be scanned "
                f"(syntax error at line {err.lineno}) - the rule fails closed"
            )
            continue
        except UnicodeDecodeError:
            violations.append(f"AD-11 single value definition: {path.name} is not valid UTF-8")
            continue
        scanned += 1

        for node in ast.walk(tree):
            # `from crm.segment.value import VALUE_COLUMN` - the column string
            # arrives bound to a local name, so no literal ever appears.
            if isinstance(node, ast.ImportFrom):
                if node.module == _VALUE_DEFINITION_DOTTED and any(
                    alias.name in _VALUE_COLUMN_ALIASES for alias in node.names
                ):
                    violations.append(
                        f"AD-11 single value definition: {module} imports the value column "
                        f"name from {_VALUE_DEFINITION_DOTTED} - consume customer_value() instead"
                    )
                continue
            # `value_module.VALUE_COLUMN` - same escape via the module object.
            if isinstance(node, ast.Attribute) and node.attr in _VALUE_COLUMN_ALIASES:
                violations.append(
                    f"AD-11 single value definition: {module} accesses .{node.attr} "
                    f"- the value column name is private to {_VALUE_DEFINITION_MODULE}"
                )
                continue
            # `df.eval("Total_Trans_Amt * 0.02")` / `df.query("Total_Trans_Amt > x")`
            # - pandas parses the column out of a larger string, so exact
            # equality cannot see it. Substring matching is safe HERE because
            # the scope is an expression argument, not arbitrary prose.
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name in _EXPRESSION_METHODS:
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            if _VALUE_COLUMN in arg.value:
                                violations.append(
                                    f"AD-11 single value definition: {module} passes "
                                    f"'{_VALUE_COLUMN}' to {name}() - consume customer_value() instead"
                                )
            # Docstrings are ast.Constant nodes too, but the comparison is
            # EXACT EQUALITY against the column name - a docstring that merely
            # mentions Total_Trans_Amt in a sentence is a different string and
            # does not match. That is what keeps prose out without needing a
            # special case, and it is why the rule is AST-based rather than a
            # substring grep.
            if isinstance(node, ast.Constant) and node.value == _VALUE_COLUMN:
                violations.append(
                    f"AD-11 single value definition: {module} references "
                    f"'{_VALUE_COLUMN}' - consume crm.segment.value.customer_value() instead"
                )
            elif isinstance(node, ast.Attribute) and node.attr == _VALUE_COLUMN:
                violations.append(
                    f"AD-11 single value definition: {module} accesses "
                    f".{_VALUE_COLUMN} - consume crm.segment.value.customer_value() instead"
                )

    return violations, scanned


def find_extra_config_files(root: Path) -> tuple[list[str], int]:
    """AD-4: crm/config.py is the only application configuration file.

    Data-artifact trees (see ``_DATA_DIRS``) are excluded: a ``.json`` written by
    a pipeline is an output, not configuration, and flagging it would make the
    guard fire on the wrong thing.
    """
    violations: list[str] = []
    scanned = 0

    for path in root.rglob("*"):
        if not path.is_file() or _is_skipped(root, path):
            continue
        relative_parts = path.relative_to(root).parts
        if relative_parts and relative_parts[0] in _DATA_DIRS:
            continue
        relative = path.relative_to(root).as_posix()
        # `.env` matching is by lowercase PREFIX: dotenv tooling loads
        # `.env.local` / `.env.production` just as eagerly as `.env`, and NTFS
        # treats `.ENV` as the same file.
        is_config = path.suffix.lower() in _CONFIG_SUFFIXES or path.name.lower().startswith(".env")
        if not is_config:
            continue
        scanned += 1
        if relative in _CONFIG_WHITELIST:
            continue
        violations.append(f"AD-4 config single source: unexpected config file '{relative}'")

    return violations, scanned
