"""Tests for the extended Nightwing phases (blueprint gaps).

Covers:
- Phase A: DNS + TLS + fingerprinting finding production.
- Phase B: semgrep / gitleaks / trivy JSON parsers.
- Phase C: content-discovery branch and full command-list construction.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from squad import security_authorized as sec
from squad.agent.nightwing import Nightwing, _host_of
from squad.security_findings import SecuritySeverity


@pytest.fixture
def authorized_loopback(tmp_path):
    old = sec.AUTHORIZED_PATH
    sec.AUTHORIZED_PATH = str(tmp_path / "authorized.yaml")
    from datetime import datetime

    rec = {
        "target": "http://127.0.0.1:9999",
        "ownership_statement": "mine",
        "added_at": datetime.now(UTC).isoformat(),
    }
    rec["sha256"] = sec._sha256_of(rec)
    sec._append_authorized(rec)
    yield "http://127.0.0.1:9999"
    sec.AUTHORIZED_PATH = old


def test_host_of_strips_scheme_path_port():
    assert _host_of("https://example.com:8443/path?q=1") == "example.com"
    assert _host_of("example.com") == "example.com"


def test_phase_a_produces_dns_and_skips_headers(tmp_path, authorized_loopback, monkeypatch):
    monkeypatch.setattr(
        "squad.agent.nightwing.socket.getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 0))],
    )
    monkeypatch.setattr("squad.agent.nightwing.Nightwing._check_headers", lambda *a, **k: None)
    monkeypatch.setattr("squad.agent.nightwing.Nightwing._check_exposed", lambda *a, **k: None)
    monkeypatch.setattr("squad.agent.nightwing.Nightwing._fingerprint", lambda *a, **k: None)
    monkeypatch.setattr("squad.agent.nightwing.Nightwing._supports_tls", lambda *a, **k: False)

    nw = Nightwing(authorized_loopback)
    fs = nw.run_phase_a()
    tools = {f.tool for f in fs}
    assert "dns-recon" in tools


def test_parse_semgrep(tmp_path, authorized_loopback):
    nw = Nightwing(authorized_loopback)
    out = '{"results": [{"path": "app.py", "extra": {"message": "Possible SQLi\\nMore", "lines": "cursor.execute(q)"}}]}'
    fs = []
    nw._parse_semgrep(out, fs)
    assert len(fs) == 1
    assert fs[0].tool == "semgrep"
    assert "SQLi" in fs[0].description


def test_parse_gitleaks(tmp_path, authorized_loopback):
    nw = Nightwing(authorized_loopback)
    out = '[{"RuleID": "aws-access-key", "File": "creds.py", "Secret": "AKIA1234567890ABCDEF12"}]'
    fs = []
    nw._parse_gitleaks(out, fs)
    assert len(fs) == 1
    assert fs[0].severity == SecuritySeverity.HIGH
    assert fs[0].tool == "gitleaks"


def test_parse_trivy(tmp_path, authorized_loopback):
    nw = Nightwing(authorized_loopback)
    out = (
        '{"Results": [{"Target": "requirements.txt", "Vulnerabilities": '
        '[{"VulnerabilityID": "CVE-2024-1", "Severity": "CRITICAL", '
        '"PkgName": "requests", "InstalledVersion": "2.0", "Title": "bad"}]}]}'
    )
    fs = []
    nw._parse_trivy(out, fs)
    assert len(fs) == 1
    assert fs[0].severity == SecuritySeverity.CRITICAL
    assert fs[0].tool == "trivy"


def test_trivy_severity_mapping(tmp_path, authorized_loopback):
    nw = Nightwing(authorized_loopback)
    assert nw._trivy_severity("critical") == SecuritySeverity.CRITICAL
    assert nw._trivy_severity("unknown") == SecuritySeverity.INFO


def test_phase_c_includes_content_discovery_when_gobuster(authorized_loopback, monkeypatch):
    monkeypatch.setattr(
        "squad.agent.nightwing.shutil.which",
        lambda x: "/usr/bin/" + x if x in ("gobuster",) else None,
    )
    nw = Nightwing(authorized_loopback)
    cmds = nw._build_phase_c_commands()
    assert any("gobuster" in c for c in cmds)


def test_phase_c_reports_missing_content_tools(authorized_loopback, monkeypatch):
    # No tools installed -> Phase C should note gobuster/zap/testssl skips but run.
    monkeypatch.setattr("squad.agent.nightwing.shutil.which", lambda x: None)
    monkeypatch.setattr("squad.agent.nightwing.subprocess.Popen", lambda *a, **k: _FakeProc())
    nw = Nightwing(authorized_loopback)
    fs = nw.run_phase_c(confirm_commands=lambda t, c: True, run_id="t1")
    tools = {f.tool for f in fs}
    assert "content-discovery" in tools
    assert "zap" in tools
    assert "testssl" in tools
    assert "nmap" not in tools  # not installed


class _FakeProc:
    def communicate(self, timeout=None):
        return ("output", None)

    def poll(self):
        return 0
