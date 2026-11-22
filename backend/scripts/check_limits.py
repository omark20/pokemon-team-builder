"""Fail if a function has more than 40 lines of code or a source file more than 300 lines.

Ruff checks complexity, branches, statements and nesting; it has no rule that counts
lines, so this script covers the two length limits. A function's lines of code leave
out blank lines, comment-only lines and its docstring. Test files obey the function
limit and are exempt from the file limit.
"""

import ast
import sys
from pathlib import Path

MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 300
CHECKED = ("app", "scripts", "tests")


def docstring_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[int]:
    """Line numbers of the function's docstring, if it has one."""
    first = node.body[0]
    is_docstring = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
    if is_docstring and isinstance(first.value.value, str):
        return set(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return set()


def code_lines(lines: list[str], node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Lines of code in the function: not blank, not only a comment, not the docstring."""
    skipped = docstring_lines(node)
    span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
    return sum(
        1
        for number in span
        if number not in skipped and lines[number - 1].strip()[:1] not in ("", "#")
    )


def problems_in(path: Path) -> list[str]:
    """Every length limit the file breaks, one message each."""
    lines = path.read_text().splitlines()
    found = []
    if path.parent.name != "tests" and len(lines) > MAX_FILE_LINES:
        found.append(f"{path}: file-too-long {len(lines)} lines, limit {MAX_FILE_LINES}")
    for node in ast.walk(ast.parse("\n".join(lines))):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            length = code_lines(lines, node)
            if length > MAX_FUNCTION_LINES:
                limit = MAX_FUNCTION_LINES
                found.append(
                    f"{path}:{node.lineno} function-too-long {node.name}: {length}, limit {limit}"
                )
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
