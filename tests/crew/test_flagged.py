"""Tests for flagged-file classification."""

from squad.crew import classify_file, flagged_files


def test_test_file_flagged():
    assert "test_files" in classify_file("tests/test_x.py")


def test_lockfile_flagged():
    assert "lockfiles" in classify_file("requirements-lock.txt")


def test_ci_workflow_flagged():
    assert "ci" in classify_file(".github/workflows/ci.yml")


def test_config_flagged():
    assert "config" in classify_file("squad.yaml")


def test_plain_source_not_flagged():
    assert classify_file("src/main.py") == set()


def test_flagged_files_filters_to_flagged_only():
    out = flagged_files(["src/main.py", "squad.yaml"])
    assert len(out) == 1
    assert out[0]["path"] == "squad.yaml"
