"""Every branching Python function in scripts/ and tests/ carries a docstring.

CodeRabbit's docstring coverage check failed on PR 87: two new test methods with a
generator expression had none. The check counts functions with a cyclomatic complexity of
at least 2, so this test refuses a function that holds a branch, a loop, a boolean operator,
an except clause, a match case or a comprehension and has no docstring.
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("scripts", "tests")
# The nodes that raise McCabe cyclomatic complexity; a with block or an assert does not.
BRANCHES = (
    ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.BoolOp,
    ast.comprehension, ast.match_case,
)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def branches(func):
    """Return True when the function body, nested functions excluded, holds a branch."""
    todo = list(func.body)
    for _ in range(100_000):
        if not todo:
            return False
        node = todo.pop()
        if isinstance(node, BRANCHES):
            return True
        if not isinstance(node, FUNCTIONS + (ast.ClassDef, ast.Lambda)):
            todo.extend(ast.iter_child_nodes(node))
    raise RuntimeError(f"{func.name}: function body exceeds the node bound")


def missing_docstrings(source, name):
    """Return 'name:line function' for each branching function without a docstring."""
    tree = ast.parse(source, filename=name)
    return [
        f"{name}:{node.lineno} {node.name}"
        for node in ast.walk(tree)
        if isinstance(node, FUNCTIONS) and branches(node) and ast.get_docstring(node) is None
    ]


class DocstringTests(unittest.TestCase):
    def test_repository_functions_have_docstrings(self):
        """Every branching function in scripts/ and tests/ has a docstring."""
        found = []
        for directory in DIRS:
            for path in sorted((ROOT / directory).rglob("*.py")):
                found += missing_docstrings(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
        self.assertEqual(found, [])

    def test_refuse_branching_function_without_docstring(self):
        """A function holding a generator expression and no docstring is reported."""
        source = "def f(lines):\n    return any(x for x in lines)\n"
        self.assertEqual(missing_docstrings(source, "x.py"), ["x.py:1 f"])

    def test_boundary_straight_line_function_needs_none(self):
        """A function without a branch passes without a docstring, like the coverage check."""
        source = "def f(x):\n    return x + 1\n"
        self.assertEqual(missing_docstrings(source, "x.py"), [])

    def test_boundary_branch_in_nested_function_counts_only_there(self):
        """A branch inside a nested function marks the nested function, not the outer one."""
        source = 'def outer():\n    def inner(x):\n        """Doc."""\n        if x:\n            return 1\n    return inner\n'
        self.assertEqual(missing_docstrings(source, "x.py"), [])


if __name__ == "__main__":
    unittest.main()
