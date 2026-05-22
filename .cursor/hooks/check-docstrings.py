#!/usr/bin/env python3
"""afterFileEdit hook that checks Python files for missing docstrings.

Reads the hook event JSON from stdin, parses the edited file's AST,
and returns additional_context listing any modules, functions, or
classes that lack docstrings.
"""

import ast
import json
import sys
from pathlib import Path


def find_missing_docstrings(filepath: str) -> list[str]:
    """Parse a Python file and return descriptions of missing docstrings.

    Args:
        filepath: Absolute or relative path to a .py file.

    Returns:
        List of human-readable strings like "function foo()" or "module".
    """
    try:
        source = Path(filepath).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    missing: list[str] = []

    if not ast.get_docstring(tree):
        missing.append("module-level docstring")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not ast.get_docstring(node):
                missing.append(f"function {node.name}()")
        elif isinstance(node, ast.ClassDef):
            if not ast.get_docstring(node):
                missing.append(f"class {node.name}")

    return missing


def main() -> None:
    """Read hook event from stdin, check docstrings, write result to stdout."""
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        json.dump({}, sys.stdout)
        return

    filepath = event.get("path") or event.get("filePath") or ""

    if not filepath or not filepath.endswith(".py"):
        json.dump({}, sys.stdout)
        return

    missing = find_missing_docstrings(filepath)

    if not missing:
        json.dump({}, sys.stdout)
        return

    items = ", ".join(missing)
    message = (
        f"Docstring compliance: {filepath} is missing docstrings for: {items}. "
        f"See the docstring-compliance skill for format and quality requirements."
    )
    json.dump({"additional_context": message}, sys.stdout)


if __name__ == "__main__":
    main()
