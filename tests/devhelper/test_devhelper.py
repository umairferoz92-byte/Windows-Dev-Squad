"""Tests for the squad.devhelper anti-pattern scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from squad.devhelper import Severity, render_report, scan_paths


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temp directory with a few source files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def test_scan_finds_secret(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.py"
    bad.write_text('password = "supersecret123"\n', encoding="utf-8")

    findings, audit = scan_paths([str(tmp_repo)])
    assert len(findings) >= 1
    assert all(f.severity == Severity.LOW for f in findings)
    assert audit.findings >= 1


def test_scan_finds_insecure_http(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.js"
    bad.write_text('const url = "http://example.com/data";\n', encoding="utf-8")

    findings, audit = scan_paths([str(tmp_repo)])
    insecure = [f for f in findings if "HTTP" in f.title]
    assert insecure, "expected an insecure-HTTP finding"


def test_scan_finds_eval_python(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.py"
    bad.write_text('result = eval("2+2")\n', encoding="utf-8")

    findings, audit = scan_paths([str(tmp_repo)])
    evals = [f for f in findings if "eval" in f.detail.lower()]
    assert evals, "expected eval() finding in Python"


def test_scan_finds_eval_javascript(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.js"
    bad.write_text('const r = eval("1+1");\n', encoding="utf-8")

    findings, audit = scan_paths([str(tmp_repo)])
    evals = [f for f in findings if "eval" in f.detail.lower()]
    assert evals, "expected eval() finding in JS"


def test_clean_file_no_findings(tmp_repo: Path) -> None:
    good = tmp_repo / "good.py"
    good.write_text("import os\n\nprint('hello')\n", encoding="utf-8")

    findings, audit = scan_paths([str(tmp_repo)])
    assert findings == []
    assert audit.findings == 0
    assert audit.severity_highest == "INFO"


def test_scan_single_file(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.py"
    bad.write_text('password = "hunter2"\n', encoding="utf-8")

    findings, audit = scan_paths([str(bad)])
    assert findings, "expected findings from single-file scan"


def test_scan_empty_list_ok() -> None:
    """scan_paths with no paths should return no findings, not crash."""
    findings, audit = scan_paths([])
    assert findings == []
    assert audit.findings == 0


def test_missing_path_skipped(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    findings, audit = scan_paths([str(missing)])
    assert findings == []
    assert audit.findings == 0


def test_render_report_empty() -> None:
    text = render_report([])
    assert "_No findings detected._" in text


def test_render_report_finds(tmp_repo: Path) -> None:
    bad = tmp_repo / "bad.py"
    bad.write_text('password = "abc123"\n', encoding="utf-8")

    findings, _ = scan_paths([str(tmp_repo)])
    text = render_report(findings)
    assert "Code Security Scan Report" in text
    assert "findings" in text.lower()
