"""Tests for Oracle, the report writer (Prompt 5).

Asserts:
- Every finding Nightwing produced appears in the report (nothing dropped).
- Oracle never changes a severity or drops a finding (only exact-repeats dedup).
- Redaction removes secret-looking strings (API keys, passwords) from evidence.
- Markdown and HTML rendering both work.
"""

from __future__ import annotations

import pytest

from squad.agent.oracle import Oracle, _finding_key, redact_evidence
from squad.security_findings import SecurityFinding, SecuritySeverity


def _finding(sev, desc="sample issue", ep="http://x/a", tool="nmap", ev=""):
    return SecurityFinding(
        tool=tool,
        severity=sev,
        description=desc,
        file_or_endpoint=ep,
        evidence_snippet=ev,
        cwe="CWE-79",
        owasp_category="A03:2021-Injection",
        remediation="Sanitize input.",
    )


def test_redact_removes_api_keys():
    src = "Authorization: Bearer sk-live-abcdef1234567890ghijklmnopqrst"
    out = redact_evidence(src)
    assert "sk-live" not in out
    assert "[REDACTED]" in out


def test_redact_removes_password_assignment():
    src = "config password = 'hunter2-secret'"
    out = redact_evidence(src)
    assert "hunter2" not in out


def test_redact_leaves_benign_text():
    src = "GET /login 200 OK, 3 headers"
    assert redact_evidence(src) == src


def test_report_contains_every_finding():
    findings = [
        _finding(SecuritySeverity.CRITICAL, "desc-1", ev="evidence A"),
        _finding(SecuritySeverity.MEDIUM, "desc-2", ep="http://y/b", tool="zap", ev="evidence B"),
        _finding(SecuritySeverity.LOW, "desc-3", ep="http://z/c", tool="bandit", ev=""),
    ]
    oracle = Oracle(findings=findings, target="http://tgt")
    md = oracle.to_markdown()
    for d in ("desc-1", "desc-2", "desc-3", "evidence A", "evidence B"):
        assert d in md, f"report missing {d}"


def test_report_never_changes_severity():
    findings = [
        _finding(SecuritySeverity.HIGH, "keep", ev="x"),
        _finding(SecuritySeverity.CRITICAL, "keep2", ev="y"),
    ]
    oracle = Oracle(findings=findings)
    # Sorted output must retain exact severities (sorted, not changed).
    sorted_ = oracle.sorted_findings()
    assert [f.severity for f in sorted_] == [SecuritySeverity.CRITICAL, SecuritySeverity.HIGH]


def test_dedupe_only_exact_repeats():
    # Two genuinely identical findings -> one kept.
    a = _finding(SecuritySeverity.MEDIUM, "same", ev="z")
    b = _finding(SecuritySeverity.MEDIUM, "same", ev="z")
    # A different severity is NOT a repeat -> kept separately.
    c = _finding(SecuritySeverity.HIGH, "same", ev="z")
    oracle = Oracle(findings=[a, b, c])
    assert len(oracle.findings) == 2
    sevs = {f.severity for f in oracle.findings}
    assert sevs == {SecuritySeverity.MEDIUM, SecuritySeverity.HIGH}


def test_redaction_applies_to_evidence_in_report():
    secret = "Authorization: Bearer ghp_0123456789abcdefghijklmn"
    findings = [_finding(SecuritySeverity.MEDIUM, "has secret", ev=secret)]
    oracle = Oracle(findings=findings)
    md = oracle.to_markdown()
    assert "ghp_0123" not in md
    assert "[REDACTED]" in md


def test_html_rendering():
    findings = [_finding(SecuritySeverity.LOW, "html-issue")]
    oracle = Oracle(findings=findings, target="http://t")
    html = oracle.to_html()
    assert html.startswith("<!DOCTYPE html>")
    assert "html-issue" in html


def test_skipped_section():
    oracle = Oracle(findings=[], target="http://t", skipped={
        "active-scan": "operator declined Phase C consent",
        "tls": "testssl.sh not installed",
    })
    md = oracle.to_markdown()
    assert "testssl.sh not installed" in md
    assert "operator declined Phase C consent" in md


def test_empty_report_has_no_findings():
    oracle = Oracle(findings=[], target="http://t")
    md = oracle.to_markdown()
    assert "No findings were reported" in md
    assert "Overall risk picture: **No significant findings**" in md