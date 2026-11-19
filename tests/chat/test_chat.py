"""Unit tests for the two-tier chatbot (offline parser + LLM routing)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from squad.chat import offline
from squad.chat.offline import parse


def test_quit_commands():
    for msg in ("exit", "quit", "bye", "q"):
        assert parse(msg).kind == "quit"


def test_help():
    assert parse("help").kind == "help"
    assert parse("what can you do").kind == "help"


def test_review_intent():
    it = parse("review C:/tmp/app.py")
    assert it.kind == "action"
    assert it.cmd == ["dev", "review", "C:/tmp/app.py"]


def test_bare_review_prompts_usage():
    """Bare 'review' must prompt for a path, not drift into LLM research."""
    it = parse("review")
    assert it.kind == "interactive"
    assert "review" in it.note


def test_bare_scan_prompts_usage():
    it = parse("scan")
    assert it.kind == "interactive"
    assert "scan" in it.note


def test_bare_refactor_prompts_usage():
    it = parse("refactor")
    assert it.kind == "interactive"
    assert "refactor" in it.note


def test_bare_testgen_prompts_usage():
    it = parse("testgen")
    assert it.kind == "interactive"
    assert "testgen" in it.note


def test_testgen_intent():
    it = parse("generate tests for utils.py")
    assert it.kind == "action"
    assert it.cmd == ["dev", "testgen", "utils.py"]


def test_refactor_intent():
    it = parse("refactor legacy.py")
    assert it.cmd == ["dev", "refactor", "legacy.py"]


def test_scan_with_repo():
    it = parse("scan http://example.com repo C:/my-app")
    assert it.kind == "action"
    assert it.cmd[0] == "security"
    assert it.cmd[1] == "nightwing"
    assert "C:/my-app" in it.cmd


def test_fetch_intel():
    assert parse("fetch intel").cmd == ["intel", "fetch"]
    assert parse("update intel feed").cmd == ["intel", "fetch"]


def test_search_intel():
    assert parse("search CWE-89").cmd == ["intel", "search", "CWE-89"]


def test_status_intel():
    it = parse("intel status")
    assert it.cmd == ["intel", "status"]


def test_doctor_history_tools():
    assert parse("doctor").cmd == ["security", "doctor"]
    assert parse("show history").cmd == ["security", "history"]
    assert parse("check tools").cmd == ["security", "check-tools"]


def test_export():
    it = parse("export run_123 as csv")
    assert it.cmd == ["security", "export", "run_123", "--format", "csv"]


def test_add_target_is_interactive():
    it = parse("add target")
    assert it.kind == "interactive"


def test_llm_routing_for_research():
    for msg in ("what is SQL injection", "explain TLS handshake", "how do I harden an API"):
        assert parse(msg).kind == "llm", msg


def test_fallback_query_strips_stopwords():
    from squad.chat import _fallback_query

    assert _fallback_query("what is SQL injection") == "SQL injection"
    assert _fallback_query("explain TLS handshake") == "TLS handshake"


def test_run_command_returns_str():
    # intel status is a safe, offline, fast command.
    out = offline.run_command(["intel", "status"], timeout=60)
    assert isinstance(out, str)
    assert "intel" in out.lower() or "feed" in out.lower()
