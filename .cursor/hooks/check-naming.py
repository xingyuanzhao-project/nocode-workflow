"""Hook script to check Python files for naming convention violations.

Reads a Cursor hook event from stdin, parses the edited file with ast,
and reports any identifiers that are single-letter or ultra-short (<=2 chars)
outside the allowed exceptions list.
"""

import ast
import json
import sys
from pathlib import Path

ALLOWED_SHORT_NAMES = frozenset({
    "i", "j", "k",          # numeric loop indices
    "e",                     # except clause binding
    "_",                     # throwaway
    "x", "y", "z",          # math/coordinates
    "n",                     # count in range()
    "f",                     # short file handle
    "T",                     # TypeVar
    "id",                    # common domain term
    "df",                    # pandas DataFrame
    "self", "cls",           # method params
    "args", "kwargs",        # variadic params
    "ok", "os", "re", "io", # stdlib module names used as imports
})

MIN_NAME_LENGTH = 3


def find_violations(source_code, file_path):
    """Parse source and return list of naming violations."""
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return []

    violations = []

    for node in ast.walk(tree):
        names_to_check = []

        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            names_to_check.append((node.name, "function", node.lineno))
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                names_to_check.append((arg.arg, "parameter", arg.lineno))
            if node.args.vararg:
                names_to_check.append((node.args.vararg.arg, "parameter", node.args.vararg.lineno))
            if node.args.kwarg:
                names_to_check.append((node.args.kwarg.arg, "parameter", node.args.kwarg.lineno))

        elif isinstance(node, ast.ClassDef):
            names_to_check.append((node.name, "class", node.lineno))

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names_to_check.append((target.id, "variable", target.lineno))
                elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
                    for element in target.elts:
                        if isinstance(element, ast.Name):
                            names_to_check.append((element.id, "variable", element.lineno))

        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names_to_check.append((node.target.id, "variable", node.target.lineno))

        elif isinstance(node, (ast.For, ast.AsyncFor)):
            if isinstance(node.target, ast.Name):
                names_to_check.append((node.target.id, "loop variable", node.target.lineno))
            elif isinstance(node.target, ast.Tuple):
                for element in node.target.elts:
                    if isinstance(element, ast.Name):
                        names_to_check.append((element.id, "loop variable", element.lineno))

        for name, kind, lineno in names_to_check:
            if name.startswith("_") and len(name) > 1:
                check_name = name.lstrip("_")
            else:
                check_name = name

            if len(check_name) < MIN_NAME_LENGTH and check_name not in ALLOWED_SHORT_NAMES:
                violations.append(
                    f"  Line {lineno}: {kind} '{name}' is too short "
                    f"({len(check_name)} chars). Use a descriptive name."
                )

    return violations


def main():
    event_data = json.load(sys.stdin)

    file_path = event_data.get("file_path", "")
    if not file_path.endswith(".py"):
        print(json.dumps({}))
        return

    path = Path(file_path)
    if not path.exists():
        print(json.dumps({}))
        return

    try:
        source_code = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print(json.dumps({}))
        return

    violations = find_violations(source_code, file_path)

    if not violations:
        print(json.dumps({}))
        return

    context_lines = [
        f"Naming violations in {path.name}:",
        *violations,
        "",
        "Names must be self-descriptive (>=3 chars unless in allowed exceptions).",
        "See .cursor/skills/naming-compliance/SKILL.md for the full policy.",
    ]

    print(json.dumps({"additional_context": "\n".join(context_lines)}))


if __name__ == "__main__":
    main()
