"""Fail if a function is longer than 40 lines or a source file longer than 300.

Ruff checks complexity, branches and nesting; it has no rule for length, so this
script covers the two size limits the project keeps. Test files obey the function
limit but are exempt from the file limit. A function's length counts its non-blank
lines, docstring included.
"""

import ast
import sys
from pathlib import Path

MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 300
CHECKED = ("app", "scripts", "tests")


def problems_in(path: Path) -> list[str]:
    """Every size limit the file breaks, one message each."""
    lines = path.read_text().splitlines()
    found = []
    if path.parent.name != "tests" and len(lines) > MAX_FILE_LINES:
        found.append(f"{path}: {len(lines)} lines, limit {MAX_FILE_LINES}")
    for node in ast.walk(ast.parse("\n".join(lines))):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            body = lines[node.lineno - 1 : node.end_lineno]
            length = sum(1 for line in body if line.strip())
            if length > MAX_FUNCTION_LINES:
                found.append(f"{path}:{node.lineno} {node.name}: {length} lines")
    return found


def main() -> int:
    """Check every Python file under app/, scripts/ and tests/; print and fail on any problem."""
    root = Path(__file__).resolve().parents[1]
    found = [p for d in CHECKED for f in sorted((root / d).rglob("*.py")) for p in problems_in(f)]
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
