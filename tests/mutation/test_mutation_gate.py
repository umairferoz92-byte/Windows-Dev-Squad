"""Tests for the mutation testing gate and enhanced dev testgen."""

from __future__ import annotations

from squad.dev import DeveloperAssistant, _sample_arg
from squad.mutation_test import compute_hash, python_mutators, run_mutations


def test_compute_hash_stable():
    assert compute_hash("abc") == compute_hash("abc")
    assert len(compute_hash("abc")) == 12


def test_mutators_change_source():
    mutators = python_mutators()
    assert len(mutators) >= 4
    # Find at least one mutator that modifies a representative source.
    source = "x = True\nif x:\n    pass\n"
    found = any((m(source) is not None) for _, m in mutators)
    assert found


def test_toggle_true_false():
    _, toggle = [m for m in python_mutators() if m[0] == "toggle_true_false"][0]
    result = toggle("flag = True")
    assert result is not None
    assert result[0] == "flag = False"


def test_add_pass_else():
    _, add_else = [m for m in python_mutators() if m[0] == "add_pass_else"][0]
    result = add_else("if x:\n    y = 1")
    assert result is not None
    assert "else:" in result[0]
    assert "pass" in result[0]


def test_sample_arg_smart():
    assert _sample_arg("count") == "5"
    assert _sample_arg("price") == "10.0"
    assert _sample_arg("enabled") == "True"
    assert _sample_arg("path") == '"sample.txt"'
    assert _sample_arg("name") == '"sample.txt"'
    assert _sample_arg("x") == "1"
    assert _sample_arg("y") == "2"


def test_enhanced_testgen_uses_signatures(tmp_path):
    src = tmp_path / "mathops.py"
    src.write_text(
        "def add(a, b):\n    return a + b\n\ndef is_enabled(flag):\n    return flag is True\n",
        encoding="utf-8",
    )
    assistant = DeveloperAssistant(cwd=str(tmp_path))
    res = assistant.generate_tests(str(src))

    assert res.tests_generated == 2
    content = res.content
    # Assertion-based test using sampled args
    assert "result = mathops.add(1, 2)" in content
    assert "result is not None" in content
    assert "mathops.is_enabled(True)" in content


def test_run_mutations_on_simple_file(tmp_path):
    target = tmp_path / "snippet.py"
    # A file with a killable mutation (if/else) so the gate has something to find.
    target.write_text("def foo(x):\n    if x > 0:\n        return 1\n    return 0\n", encoding="utf-8")
    # Use a test command that will always fail the mutation (a fake strict test).
    run = run_mutations(str(target), test_cmd=["python", "-c", "import sys; sys.exit(1)"])
    assert run.killed >= 1
    # Original restored after runs.
    assert target.read_text(encoding="utf-8") == "def foo(x):\n    if x > 0:\n        return 1\n    return 0\n"
