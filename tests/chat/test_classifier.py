"""Tests for the TF intent/security classifier bridge + chat routing.

The bridge degrades gracefully: if TensorFlow or the model artifacts are
missing, ``available`` is False and routing returns None (never raises). This
keeps the chatbot fully functional in offline installs while still unlocking
ML-based routing when the models exist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from squad.chat import classifier as clfmod
from squad.chat.classifier import _LABEL_CMD, _extract_arg


def test_bridge_never_raises_on_missing_models(monkeypatch):
    # Force the loader to fail so we exercise the degraded path.
    monkeypatch.setattr(clfmod, "_load", lambda which: None)
    b = clfmod.ClassifierBridge()
    b._loaded = False  # force re-load through the patched loader
    assert b.available is False
    assert b.intent("status") == (None, 0.0)
    assert b.security("eval(x)") is None
    assert b.route("status") is None


def test_bridge_degradation_when_tf_missing(monkeypatch):
    def boom(which):
        raise ImportError("tensorflow not installed")

    monkeypatch.setattr(clfmod, "_load", boom)
    b = clfmod.ClassifierBridge()
    assert b.available is False
    assert b.route("anything") is None


def test_extract_arg_finds_pathy_token():
    # A bare action word should NOT be treated as a target.
    assert _extract_arg("review this file for bugs", "review") is None
    # A real path should be found even mid-sentence.
    assert _extract_arg("review C:/code/app.py", "review") == "C:/code/app.py"
    assert _extract_arg("generate tests for utils.py", "testgen") == "utils.py"


def test_extract_arg_repo_preferred():
    assert _extract_arg("scan http://example.com repo C:/my-app", "scan") == "C:/my-app"


def test_extract_arg_url_ip():
    assert _extract_arg("scan http://example.com", "scan") == "http://example.com"
    assert _extract_arg("scan 10.0.0.4", "scan") == "10.0.0.4"


def test_label_cmd_has_arg_slots_for_arg_needing_labels():
    for label in ("review", "testgen", "refactor", "scan", "search", "export"):
        assert "{arg}" in _LABEL_CMD[label], label


def test_looks_like_code_check_positive():
    assert clfmod.looks_like_code_check("check if this code is safe: eval(x)")
    assert clfmod.looks_like_code_check("review conn.execute(query) for vulnerabilities")
    assert clfmod.looks_like_code_check("is this snippet vulnerable? cur.execute(...)")


def test_looks_like_code_check_negative():
    assert not clfmod.looks_like_code_check("review C:/code/app.py")  # file review, not snippet
    assert not clfmod.looks_like_code_check("what is sql injection")
    assert not clfmod.looks_like_code_check("security status")


def test_security_verdict_none_on_empty():
    assert clfmod.security_verdict("") is None
    assert clfmod.security_verdict("   ") is None


def test_code_security_routes_through_handle(monkeypatch):
    import squad.chat as chatmod
    import squad.chat.classifier as clf
    from squad.chat import offline

    calls = {}

    def fake_verdict(code):
        calls["code"] = code
        return (0.99, "vulnerable")

    monkeypatch.setattr(chatmod, "_try_classifier_route", lambda t: None)
    monkeypatch.setattr(clf, "security_verdict", fake_verdict)
    monkeypatch.setattr(clf, "looks_like_code_check", lambda t: True)
    out = chatmod._handle(offline.parse("check if this code is safe: eval(x)"))
    assert calls["code"] == "eval(x)"
    assert "VULNERABLE" in out


def test_extract_snippet_after_separator():
    from squad.chat.__init__ import _extract_snippet

    assert _extract_snippet("check code: eval(x)") == "eval(x)"
    assert _extract_snippet("is this snippet safe: cur.execute(u)") == "cur.execute(u)"


def test_label_cmd_no_arg_for_status_doctor_tools_fetch():
    for label in ("status", "doctor", "tools", "fetch"):
        assert "{arg}" not in _LABEL_CMD[label], label


def test_route_returns_none_below_threshold(monkeypatch):
    b = clfmod.ClassifierBridge()
    b._intent = _FakeIntent("status", 0.3)
    b._security = None
    b._loaded = True
    assert b.route("status") is None


def test_route_returns_command_on_confident_hit(monkeypatch):
    b = clfmod.ClassifierBridge()
    b._intent = _FakeIntent("status", 0.9)
    b._security = None
    b._loaded = True
    assert b.route("status") == ["security", "status"]


class _FakeIntent:
    def __init__(self, label, conf):
        self.label, self.conf = label, conf

    def predict(self, text):
        return self.label, self.conf
