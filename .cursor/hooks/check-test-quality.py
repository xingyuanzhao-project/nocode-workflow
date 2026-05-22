"""Hook script that warns when a test file contains suspicious low-quality patterns.

Reads a file-edit event from stdin, parses the target file with ast, and returns
additional_context if red flags are detected (no-assert tests, existence-only
assertions, import-only test bodies).
"""

import ast
import json
import sys
import os


def is_test_file(filepath: str) -> bool:
    """Determine if a file is a Python test file by name or directory."""
    basename = os.path.basename(filepath)
    if basename.startswith("test_") and basename.endswith(".py"):
        return True
    if basename.endswith("_test.py"):
        return True
    parts = filepath.replace("\\", "/").split("/")
    if "tests" in parts or "test" in parts:
        return basename.endswith(".py")
    return False


def get_test_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Extract all top-level and class-level test functions."""
    test_funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_") or node.name.startswith("test"):
                test_funcs.append(node)
    return test_funcs


def has_assert(func: ast.FunctionDef) -> bool:
    """Check if a function contains any assert statement or pytest.raises."""
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            func_attr = node.func
            if isinstance(func_attr, ast.Attribute) and func_attr.attr == "raises":
                return True
            if isinstance(func_attr, ast.Name) and func_attr.id == "raises":
                return True
        if isinstance(node, ast.With):
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call):
                    if isinstance(ctx.func, ast.Attribute) and ctx.func.attr == "raises":
                        return True
    return False


def is_only_none_check(func: ast.FunctionDef) -> bool:
    """Check if all assertions in the function are only 'is not None' or 'is True'."""
    asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
    if not asserts:
        return False

    for a in asserts:
        test_expr = a.test
        if isinstance(test_expr, ast.Compare):
            for op in test_expr.ops:
                if isinstance(op, ast.IsNot):
                    for comp in test_expr.comparators:
                        if isinstance(comp, ast.Constant) and comp.value is None:
                            continue
                        return False
                elif isinstance(op, ast.Is):
                    for comp in test_expr.comparators:
                        if isinstance(comp, ast.Constant) and comp.value is True:
                            continue
                        return False
                else:
                    return False
        elif isinstance(test_expr, ast.Name) or isinstance(test_expr, ast.Attribute):
            continue  # assert obj — truthiness check, weak
        else:
            return False
    return True


def is_import_only(func: ast.FunctionDef) -> bool:
    """Check if a test function body only contains imports (and maybe pass)."""
    for node in func.body:
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            continue
        if isinstance(node, ast.Pass):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # docstring
        return False
    return True


def analyze_test_file(filepath: str) -> list[str]:
    """Parse a test file and return list of quality warnings."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    test_funcs = get_test_functions(tree)
    if not test_funcs:
        return []

    warnings = []

    for func in test_funcs:
        line = func.lineno
        name = func.name

        if is_import_only(func):
            warnings.append(
                f"  - `{name}` (line {line}): body is import-only with no "
                f"function calls or assertions — this is not a real test"
            )
            continue

        if not has_assert(func):
            warnings.append(
                f"  - `{name}` (line {line}): no assert statements — "
                f"a test must validate outputs, not just run without crashing"
            )
            continue

        if is_only_none_check(func):
            warnings.append(
                f"  - `{name}` (line {line}): only asserts `is not None` or "
                f"`is True` — test must validate actual computed values"
            )

    return warnings


def main():
    event = json.load(sys.stdin)
    filepath = event.get("file_path", "")

    if not filepath or not is_test_file(filepath):
        print(json.dumps({}))
        return

    if not os.path.isfile(filepath):
        print(json.dumps({}))
        return

    warnings = analyze_test_file(filepath)

    if not warnings:
        print(json.dumps({}))
        return

    warning_text = (
        "## Test Quality Warning\n\n"
        "The following test functions appear to be superficial "
        "(no meaningful assertions or import-only bodies). "
        "Tests must validate actual outputs, state changes, or side effects — "
        "not just prove code is importable or doesn't crash.\n\n"
        + "\n".join(warnings)
        + "\n\n"
        "Refer to the testing-standards skill for required test patterns."
    )

    print(json.dumps({"additional_context": warning_text}))


if __name__ == "__main__":
    main()
