"""Static guards for the architecture rules the whole design depends on:
Core never imports MT5 or knows about adapters/backend, and MetaTrader5 is
only ever imported from adapters/mt5/. These are cheap to check statically
and catch a regression immediately, before it needs a running MT5 to find.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORE_DIR = REPO_ROOT / "core"


def _all_py_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_metatrader5_is_only_imported_inside_adapters_mt5():
    offenders = []
    for path in _all_py_files(REPO_ROOT):
        if "/.venv/" in str(path) or "/adapters/mt5/" in str(path):
            continue
        if "MetaTrader5" in _imported_module_names(path):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"MetaTrader5 imported outside adapters/mt5/: {offenders}"


def test_core_never_imports_adapters_or_backend():
    offenders = []
    for path in _all_py_files(CORE_DIR):
        modules = _imported_module_names(path)
        if "adapters" in modules or "backend" in modules:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"core/ importing adapters/backend (dependency direction violated): {offenders}"


def test_strategies_never_import_metatrader5_or_adapters():
    strategies_dir = CORE_DIR / "strategies"
    offenders = []
    for path in _all_py_files(strategies_dir):
        modules = _imported_module_names(path)
        if "MetaTrader5" in modules or "adapters" in modules:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"strategy code depends on MT5/adapters directly: {offenders}"


def test_mt5_execution_adapter_never_calls_a_real_order_function():
    """Guards against v1 accidentally gaining real trade execution: every
    method must raise, none may call an mt5.order_send-style function."""
    path = REPO_ROOT / "adapters" / "mt5" / "mt5_execution_adapter.py"
    source = path.read_text()
    assert "order_send" not in source
    assert "NotImplementedError" in source
