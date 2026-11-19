"""Tests for the product-feature additions: store, compliance, roles,
notifications, doctor, config, and the extended manifest checksum.
"""

from __future__ import annotations

import os

from squad.compliance import map_controls, summary_controls, to_csv, to_jira_json
from squad.config.squadcfg import load_config
from squad.roles import can, export_audit, set_role, verify_audit_export
from squad.security_findings import SecurityFinding, SecuritySeverity
from squad.store.history import store_for_testing
from squad.tools.manifest import ToolManifestEntry, sha256_file, verify_checksum


def _finding(sev, desc="issue", ep="http://x", owasp="A03:2021-Injection"):
    return SecurityFinding("nmap", sev, desc, ep, owasp_category=owasp)


# ---------------------------------------------------------------------------
# ScanStore / history / diff / gate
# ---------------------------------------------------------------------------
def test_store_new_run_and_findings(tmp_path):
    store = store_for_testing(tmp_path)
    run = store.new_run("http://t", "ab")
    store.add_findings(run, [_finding(SecuritySeverity.HIGH), _finding(SecuritySeverity.LOW)])
    assert store.get_run(run)["target"] == "http://t"
    assert len(store.run_findings(run)) == 2
    assert store.count_by_severity(run)["high"] == 1


def test_store_redacts_evidence_at_rest(tmp_path):
    # F1 regression: secrets in evidence_snippet must not survive in the DB.
    store = store_for_testing(tmp_path)
    run = store.new_run("http://t", "ab")
    leaky = SecurityFinding(
        "gitleaks",
        SecuritySeverity.HIGH,
        "hardcoded secret",
        "http://x",
        evidence_snippet="AKIAIOSFODNN7EXAMPLE ghp_0123456789abcdefghij ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGH",
    )
    store.add_findings(run, [leaky])
    stored = store.run_findings(run)[0]
    assert "[REDACTED]" in stored["evidence_snippet"]
    assert "AKIA" not in stored["evidence_snippet"]
    assert "ghp_" not in stored["evidence_snippet"]


def test_store_diff(tmp_path):
    store = store_for_testing(tmp_path)
    a = store.new_run("http://t", "ab")
    store.add_findings(
        a,
        [
            _finding(SecuritySeverity.HIGH, "old-issue", "http://x/old"),
            _finding(SecuritySeverity.MEDIUM, "keep", "http://x/keep"),
        ],
    )
    b = store.new_run("http://t", "ab")
    store.add_findings(
        b,
        [
            _finding(SecuritySeverity.MEDIUM, "keep", "http://x/keep"),
            _finding(SecuritySeverity.HIGH, "new-issue", "http://x/new"),
        ],
    )
    d = store.diff(a, b)
    assert any("new-issue" in str(x) for x in d["new"])
    assert any("old-issue" in str(x) for x in d["fixed"])


def test_store_gate(tmp_path):
    store = store_for_testing(tmp_path)
    run = store.new_run("http://t", "ab")
    store.add_findings(
        run,
        [
            _finding(SecuritySeverity.CRITICAL, "bad", "http://x"),
            _finding(SecuritySeverity.LOW, "ok", "http://y"),
        ],
    )
    passed, blockers = store.gate(run, fail_on="high")
    assert passed is False
    assert len(blockers) == 1

    # Mark the critical as accepted -> gate passes.
    row = store.run_findings(run, status=None)[0]
    store.set_status(row["id"], "accepted")
    passed, blockers = store.gate(run, fail_on="high")
    assert passed is True


# ---------------------------------------------------------------------------
# Compliance mapping + export
# ---------------------------------------------------------------------------
def test_map_controls():
    c = map_controls("A03:2021-Injection")
    assert c["nist"] == "SI-10 Information Input Validation"
    assert c["iso"].startswith("A.14.2.1")
    assert c["pci"].startswith("6.5.1")
    # Unknown category -> blanks, not crash.
    assert map_controls("") == {"nist": "", "iso": "", "pci": ""}


def test_summary_controls_aggregates():
    fs = [
        _finding(SecuritySeverity.HIGH, owasp="A03:2021-Injection"),
        _finding(SecuritySeverity.LOW, owasp="A05:2021-Security Misconfiguration"),
    ]
    s = summary_controls(fs)
    assert "SI-10 Information Input Validation" in s["nist"]
    assert len(s["nist"]) == 2


def test_to_csv_contains_header_and_rows():
    csv_text = to_csv([_finding(SecuritySeverity.HIGH)])
    assert "severity,tool,description" in csv_text
    assert "nmap" in csv_text
    assert "high" in csv_text


def test_to_jira_json_valid():
    data = __import__("json").loads(to_jira_json([_finding(SecuritySeverity.MEDIUM)]))
    assert len(data) == 1
    assert "[MEDIUM]" in data[0]["summary"]
    assert data[0]["custom"]["nist"]


# ---------------------------------------------------------------------------
# Roles + signed audit export
# ---------------------------------------------------------------------------
def test_roles_access_matrix(tmp_path):
    set_role("auditor", path=str(tmp_path / "roles.json"))
    assert can("export_audit", "auditor") is True
    assert can("add_target", "auditor") is False
    assert can("add_target", "owner") is True


def test_signed_audit_roundtrip(tmp_path):
    lines = ['{"event": "a"}', '{"event": "b"}', '{"event": "c"}']
    signed = export_audit(lines)
    ok, count = verify_audit_export(signed)
    assert ok is True
    assert count == 3


def test_signed_audit_detects_tamper(tmp_path):
    signed = export_audit(['{"event": "a"}', '{"event": "b"}'])
    tampered = signed.replace('"event": "b"', '"event": "EVIL"')
    ok, _ = verify_audit_export(tampered)
    assert ok is False


# ---------------------------------------------------------------------------
# Config (squad.toml)
# ---------------------------------------------------------------------------
def test_load_config_defaults_when_missing(tmp_path):
    c = load_config(os.path.join(str(tmp_path), "none.toml"))
    assert c.rate_limit_rps == 2.0
    assert c.fail_on == "high"
    assert c.default_phases == "ab"


def test_load_config_parses_toml(tmp_path):
    p = os.path.join(str(tmp_path), "squad.toml")
    with open(p, "w") as f:
        f.write("[scan]\nrate_limit_rps = 5.0\nfail_on = 'critical'\n[tools]\nsemgrep = false\n[notify]\nchannel = 'desktop'\n")
    c = load_config(p)
    assert c.rate_limit_rps == 5.0
    assert c.fail_on == "critical"
    assert c.use_semgrep is False
    assert c.notify_channel == "desktop"


# ---------------------------------------------------------------------------
# Manifest checksum verification
# ---------------------------------------------------------------------------
def test_verify_checksum_matches(tmp_path):
    f = tmp_path / "tool.bin"
    f.write_bytes(b"hello binary")
    entry = ToolManifestEntry(name="x", display="X", purpose="p", binary="x", install_cmd="", sha256=sha256_file(str(f)))
    ok, detail = verify_checksum(entry, str(f))
    assert ok is True
    assert "verified" in detail


def test_verify_checksum_mismatch(tmp_path):
    f = tmp_path / "tool.bin"
    f.write_bytes(b"hello binary")
    entry = ToolManifestEntry(name="x", display="X", purpose="p", binary="x", install_cmd="", sha256="0" * 64)
    ok, detail = verify_checksum(entry, str(f))
    assert ok is False


def test_verify_checksum_no_checksum(tmp_path):
    f = tmp_path / "tool.bin"
    f.write_bytes(b"x")
    entry = ToolManifestEntry(name="x", display="X", purpose="p", binary="x", install_cmd="")
    ok, detail = verify_checksum(entry, str(f))
    assert ok is True  # "no published checksum" is not a failure
