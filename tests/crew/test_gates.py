"""Tests for gate evaluation."""

from squad.crew import evaluate_gates, gates_all_pass


def test_all_gates_pass():
    prev = {"tests_passed": 5, "tests_skipped": 0, "coverage": 80.0, "exit_code": 0}
    curr = {"tests_passed": 6, "tests_skipped": 0, "coverage": 82.0, "exit_code": 0}
    assert gates_all_pass(evaluate_gates(prev, curr, [])) is True


def test_failing_tests_fail_gate():
    curr = {"tests_passed": 6, "tests_skipped": 0, "coverage": 82.0, "exit_code": 1}
    gates = evaluate_gates({}, curr, [])
    assert any(g.name == "tests_exit_0" and not g.passed for g in gates)


def test_test_count_not_lower_fails():
    prev = {"tests_passed": 6}
    curr = {"tests_passed": 5, "exit_code": 0, "coverage": 0.0}
    gates = evaluate_gates(prev, curr, [])
    assert any(g.name == "test_count_not_lower" and not g.passed for g in gates)


def test_coverage_not_lower_fails():
    prev = {"tests_passed": 1, "coverage": 80.0}
    curr = {"tests_passed": 1, "coverage": 75.0, "exit_code": 0}
    gates = evaluate_gates(prev, curr, [])
    assert any(g.name == "coverage_not_lower" and not g.passed for g in gates)


def test_unresolved_high_finding_fails():
    gates = evaluate_gates({}, {}, [{"severity": "high", "approved": False}])
    assert any(g.name == "no_unresolved_high_critical" and not g.passed for g in gates)


def test_approved_high_finding_ok():
    gates = evaluate_gates({}, {}, [{"severity": "high", "approved": True}])
    assert any(g.name == "no_unresolved_high_critical" and g.passed for g in gates)
