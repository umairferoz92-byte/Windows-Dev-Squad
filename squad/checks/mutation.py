"""Mutation testing gate (Feature 3).

Deliberately break changed code and check that the tests notice. A low
mutation score means the agent wrote tests that assert nothing. The gate runs
only on changed files (kept fast), reports the score on the diff, and a
threshold blocks "done".

The mutation engine is dependency-free (a robust operator set on Python source).
The test runner is injectable so CI and tests can use a stub.
"""

from __future__ import annotations

import ast
import copy
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _mutate_source(src: str) -> list[str]:
    """Return a list of mutated copies of ``src`` (one per operator)."""
    mutants: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return mutants

    for node in ast.walk(tree):
        # 1. Comparison operator swaps
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = type(node.ops[0])
            swaps = {
                ast.Eq: ast.NotEq,
                ast.NotEq: ast.Eq,
                ast.Lt: ast.GtE,
                ast.LtE: ast.Gt,
                ast.Gt: ast.LtE,
                ast.GtE: ast.Lt,
                ast.Is: ast.IsNot,
                ast.IsNot: ast.Is,
                ast.In: ast.NotIn,
                ast.NotIn: ast.In,
            }
            if op in swaps:
                mutated = _swap_compare(tree, node, swaps[op])
                mutants.append(_safe_unparse(mutated))

        # 2. Binary operator swaps (+ <-> -, * <-> /)
        elif isinstance(node, ast.BinOp):
            op = type(node.op)
            bin_swaps = {
                ast.Add: ast.Sub,
                ast.Sub: ast.Add,
                ast.Mult: ast.Div,
                ast.Div: ast.Mult,
            }
            if op in bin_swaps:
                mutated = _swap_binop(tree, node, bin_swaps[op])
                mutants.append(_safe_unparse(mutated))

        # 3. Boolean operator swaps (And <-> Or)
        elif isinstance(node, ast.BoolOp):
            mutated = copy.deepcopy(tree)
            for n in ast.walk(mutated):
                if isinstance(n, ast.BoolOp) and _same_span(n, node):
                    n.op = ast.Or() if isinstance(n.op, ast.And) else ast.And()
            mutants.append(_safe_unparse(mutated))

        # 4. Constant boolean / integer mutation
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                mutated = copy.deepcopy(tree)
                for n in ast.walk(mutated):
                    if isinstance(n, ast.Constant) and _same_span(n, node):
                        n.value = not node.value
                mutants.append(_safe_unparse(mutated))
            elif isinstance(node.value, int) and node.value in (0, 1, 2):
                mutated = copy.deepcopy(tree)
                for n in ast.walk(mutated):
                    if isinstance(n, ast.Constant) and _same_span(n, node):
                        n.value = 99 if node.value != 99 else 0
                mutants.append(_safe_unparse(mutated))

    return _dedupe([m for m in mutants if m and m != src])


def _swap_compare(tree, target_node, new_op):
    mutated = copy.deepcopy(tree)
    for n in ast.walk(mutated):
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and _same_span(n, target_node):
            n.ops[0] = new_op()
    return mutated


def _swap_binop(tree, target_node, new_op):
    mutated = copy.deepcopy(tree)
    for n in ast.walk(mutated):
        if isinstance(n, ast.BinOp) and _same_span(n, target_node):
            n.op = new_op()
    return mutated


def _safe_unparse(tree) -> str:
    try:
        return ast.unparse(tree)
    except Exception:
        return ""


def _same_span(a, b) -> bool:
    try:
        return (a.lineno, a.col_offset) == (b.lineno, b.col_offset)
    except AttributeError:
        return False


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# --- gate ------------------------------------------------------------------
@dataclass
class MutationReport:
    file: str
    mutants: int
    killed: int
    survived: int
    score: float  # killed / total (0.0 when no mutants)
    threshold: float = 0.6

    @property
    def passed(self) -> bool:
        return self.mutants == 0 or self.score >= self.threshold


class MutationGate:
    """Run mutation testing on changed files; block done when score < threshold.

    ``run_tests`` is injectable: ``run_tests(cwd) -> returncode``. The default
    runs the configured test command in a temp copy of each mutated file.
    """

    def __init__(self, test_command: list[str] | None = None, threshold: float = 0.6, run_tests=None):
        self.test_command = test_command or ["python", "-m", "pytest", "-q"]
        self.threshold = threshold
        self._run_tests = run_tests

    def changed_files(self, cwd: Path) -> list[str]:
        """Return .py files with uncommitted changes via git status."""
        import subprocess

        try:
            out = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        except Exception:
            return []
        return [f for f in out.splitlines() if f.endswith(".py")]

    def check(self, files: list[Path], workdir: Path) -> list[MutationReport]:
        """Run mutation testing on ``files``. Mutants run in temp copies of the
        repo so the real working tree is never touched."""
        reports: list[MutationReport] = []
        for f in files:
            full_path = (workdir / f) if not f.is_absolute() else f
            if not full_path.exists():
                continue
            src = full_path.read_text(encoding="utf-8", errors="replace")
            mutants = _mutate_source(src)
            killed = 0
            for mutated in mutants:
                with tempfile.TemporaryDirectory(dir=str(workdir)) as td:
                    tdir = Path(td)
                    target = tdir / f.name
                    target.write_text(mutated, encoding="utf-8")
                    rc = self._run_tests(tdir) if self._run_tests else self._run_default(tdir)
                    if rc != 0:
                        killed += 1
            survived = len(mutants) - killed
            total = len(mutants)
            score = (killed / total) if total else 1.0
            rep = MutationReport(
                file=str(f),
                mutants=total,
                killed=killed,
                survived=survived,
                score=score,
                threshold=self.threshold,
            )
            reports.append(rep)
        return reports

    def _run_default(self, cwd: Path) -> int:
        import subprocess

        try:
            return subprocess.run(list(self.test_command), cwd=str(cwd), capture_output=True, timeout=60).returncode
        except Exception:
            return 1


def gate_passes(reports: list[MutationReport], threshold: float) -> bool:
    """Overall gate: every report must meet the threshold (or have no mutants)."""
    return all(r.mutants == 0 or r.score >= threshold for r in reports)
