"""Tests for the `squad check` report."""

from squad.checks.check import CheckResult
from squad.report.report import build_report, render_report


def _result(name, returncode, verdict="allow"):
    return CheckResult(name, "run_" + name, ("cmd",), verdict, returncode, False, "", "")


def test_build_report_summary():
    results = [_result("test", 0), _result("lint", 1)]
    report = build_report(results, "/repo")
    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1, "denied": 0}
    assert "typecheck" in report["not_checked"]
    assert "security_scan" in report["not_checked"]


def test_build_report_counts_denied():
    results = [_result("test", None, verdict="deny")]
    report = build_report(results, "/repo")
    assert report["summary"]["denied"] == 1


def test_render_report_shows_status_and_summary():
    results = [_result("test", 0), _result("lint", 1)]
    text = render_report(build_report(results, "/repo"))
    assert "[PASS]" in text
    assert "[FAIL]" in text
    assert "1 passed, 1 failed" in text
    assert "Not checked" in text
