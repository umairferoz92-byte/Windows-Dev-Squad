"""Gate evaluation for a run ("done" requires all gates)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


def evaluate_gates(prev: dict, curr: dict, findings: list[dict]) -> list[GateResult]:
    """prev/curr: {"tests_passed": int, "tests_skipped": int, "coverage": float, "exit_code": int}.
    findings: list of {"severity": str, "approved": bool}."""
    gates = [
        GateResult("tests_exit_0", curr.get("exit_code") == 0, f"exit code {curr.get('exit_code')}"),
        GateResult(
            "test_count_not_lower",
            curr.get("tests_passed", 0) >= prev.get("tests_passed", 0),
            f"{prev.get('tests_passed', 0)} -> {curr.get('tests_passed', 0)}",
        ),
        GateResult(
            "coverage_not_lower",
            curr.get("coverage", 0.0) >= prev.get("coverage", 0.0),
            f"{prev.get('coverage', 0.0)} -> {curr.get('coverage', 0.0)}",
        ),
    ]
    unresolved = [f for f in findings if f.get("severity") in ("high", "critical") and not f.get("approved")]
    gates.append(
        GateResult(
            "no_unresolved_high_critical",
            len(unresolved) == 0,
            f"{len(unresolved)} unresolved high/critical finding(s)",
        )
    )
    return gates


def gates_all_pass(gates: list[GateResult]) -> bool:
    return all(g.passed for g in gates)
