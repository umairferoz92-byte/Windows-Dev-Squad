"""Mutation testing gate (Feature 3)."""

from squad.checks.mutation import MutationGate, MutationReport, _mutate_source, gate_passes


def test_mutate_source_negates_equality():
    mutants = _mutate_source("def f(x):\n    return x == 1\n")
    assert mutants, "expected at least one mutant"
    assert any("!= 1" in m for m in mutants)


def test_mutate_source_flips_true_to_false():
    mutants = _mutate_source("def f():\n    return True\n")
    assert any("return False" in m for m in mutants)


def test_mutate_and_to_or():
    mutants = _mutate_source("def f(a, b):\n    return a and b\n")
    assert any("a or b" in m for m in mutants)


def test_gate_surviving_mutant_fails_below_threshold(tmp_path):
    # a test that asserts nothing => mutant survives => low score
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a == b\n", encoding="utf-8")

    def always_pass(cwd):  # tests never catch the mutation
        return 0

    gate = MutationGate(threshold=0.6, run_tests=always_pass)
    reports = gate.check([target], workdir=tmp_path)
    assert reports, "expected a report"
    assert reports[0].killed == 0
    assert reports[0].score == 0.0
    assert gate_passes(reports, 0.6) is False
    assert reports[0].passed is False


def test_gate_killed_mutant_passes_above_threshold(tmp_path):
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a == b\n", encoding="utf-8")

    def catches_mutation(cwd):  # tests notice the break
        return 1

    gate = MutationGate(threshold=0.6, run_tests=catches_mutation)
    reports = gate.check([target], workdir=tmp_path)
    assert reports[0].killed == reports[0].mutants
    assert reports[0].score == 1.0
    assert gate_passes(reports, 0.6) is True


def test_report_has_score_on_diff_fields():
    r = MutationReport(file="a.py", mutants=2, killed=1, survived=1, score=0.5)
    r.threshold = 0.6
    assert r.passed is False


def test_changed_files_uses_git_diff(tmp_path):
    # not a git repo => no changed files listed, gate stays fast
    gate = MutationGate()
    assert gate.changed_files(tmp_path) == []
