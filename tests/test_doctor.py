"""Unit tests for the read-only ``squad doctor`` detection logic."""

from squad.cli import doctor


def test_redact_proxy_value_with_credentials():
    assert doctor.redact_proxy_value("http://alice:hunter2@proxy.corp:8080") == ("http://***@proxy.corp:8080")


def test_redact_proxy_value_without_credentials_unchanged():
    assert doctor.redact_proxy_value("http://proxy.corp:8080") == "http://proxy.corp:8080"


def test_redact_proxy_value_no_scheme_unchanged():
    assert doctor.redact_proxy_value("localhost:3128") == "localhost:3128"


def test_scrubbed_env_removes_secret_named_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-secret")
    monkeypatch.setenv("MY_PASSWORD", "hunter2")
    monkeypatch.setenv("KEEP_ME", "value")
    clean = doctor.scrubbed_env()
    assert "OPENROUTER_API_KEY" not in clean
    assert "GITHUB_TOKEN" not in clean
    assert "MY_PASSWORD" not in clean
    assert clean.get("KEEP_ME") == "value"


def test_collect_git_detects_installed():
    def fake_runner(cmd, timeout):
        return doctor.CommandResult(0, "git version 2.47.1.windows.1\n", "")

    facts = doctor.collect_git(fake_runner)
    assert facts["installed"] is True
    assert "git version" in facts["version"]


def test_collect_git_detects_missing():
    def fake_runner(cmd, timeout):
        return doctor.CommandResult(1, "", "git: not found\n")

    facts = doctor.collect_git(fake_runner)
    assert facts["installed"] is False


def test_collect_tools_finds_pytest():
    tools = doctor.collect_tools()
    assert tools["pytest"]["importable"] is True


def test_collect_proxy_redacts(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://u:p@host:80")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    proxy = doctor.collect_proxy()
    assert proxy["HTTP_PROXY"]["set"] is True
    assert proxy["HTTP_PROXY"]["value"] == "http://***@host:80"
    assert proxy["HTTPS_PROXY"]["set"] is False


def test_sandbox_edition_supported():
    assert doctor.sandbox_edition_supported("Professional") is True
    assert doctor.sandbox_edition_supported("Windows 11 Pro") is True
    assert doctor.sandbox_edition_supported("Home") is False
    assert doctor.sandbox_edition_supported(None) is False


def test_level1_available_requires_user_and_verified_marker():
    assert doctor.level1_available(True, {"verified": True}) is True
    assert doctor.level1_available(True, {"verified": False}) is False
    assert doctor.level1_available(True, None) is False
    assert doctor.level1_available(False, {"verified": True}) is False


def test_collect_isolation_has_all_levels():
    def fake_runner(cmd, timeout):
        return doctor.CommandResult(1, "", "unavailable")

    os_info = {
        "system": "Windows",
        "release": "11",
        "version": "",
        "machine": "AMD64",
        "edition": "Pro",
    }
    levels = doctor.collect_isolation(fake_runner, os_info, low_priv_user="squad-agent", marker_path=None)
    for level in ("0", "1", "2", "3", "4"):
        assert level in levels
        assert "name" in levels[level]
        assert "available" in levels[level]
        assert "detail" in levels[level]


def test_read_marker_roundtrip(tmp_path):
    path = tmp_path / "marker.json"
    path.write_text('{"user": "squad-agent", "verified": true}', encoding="utf-8")
    assert doctor._read_marker(str(path)) == {"user": "squad-agent", "verified": True}


def test_read_marker_invalid(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert doctor._read_marker(str(bad)) is None
    assert doctor._read_marker(str(tmp_path / "missing.json")) is None
