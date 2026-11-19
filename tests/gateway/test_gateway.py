"""Tests for the gateway's security (offline, FastAPI TestClient)."""

from fastapi.testclient import TestClient

from squad.gateway import create_app
from squad.gateway.controller import RemoteController


def _client(**kw):
    kw.setdefault("allowed_hosts", ("testserver",))
    return TestClient(create_app(RemoteController(), **kw))


def test_unauthenticated_status_401():
    assert _client().get("/api/status").status_code == 401


def test_wrong_host_403():
    assert _client().get("/", headers={"Host": "evil.com"}).status_code == 403


def test_csp_header_present():
    assert "Content-Security-Policy" in _client().get("/").headers


def test_login_then_status_ok():
    client = _client(login_check=lambda: True)
    token = client.post("/api/login").json()["token"]
    assert client.get("/api/status", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_login_rejected():
    assert _client(login_check=lambda: False).post("/api/login").status_code == 401


def test_rate_limited():
    client = _client(login_check=lambda: True, rate_limit=2, rate_window=60)
    client.post("/api/login")
    client.post("/api/login")
    assert client.post("/api/login").status_code == 429


def test_state_changing_requires_csrf():
    client = _client(login_check=lambda: True)
    token = client.post("/api/login").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/stop", headers=headers).status_code == 403


def test_install_not_approvable_from_web():
    client = _client(login_check=lambda: True, approvable_actions=("some_benign",))
    token = client.post("/api/login").json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": "csrf"}
    resp = client.post("/api/approve", json={"action": "install_dependencies", "approval_id": "x"}, headers=headers)
    assert resp.status_code == 403


def test_approve_allowlisted_action():
    client = _client(login_check=lambda: True, approvable_actions=("some_benign",))
    token = client.post("/api/login").json()["token"]
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": "csrf"}
    resp = client.post("/api/approve", json={"action": "some_benign", "approval_id": "x"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["approved"] is True


def test_idle_gateway_returns_503():
    ctrl = RemoteController(idle_timeout_seconds=0)  # immediately idle
    client = TestClient(create_app(ctrl, allowed_hosts=("testserver",)))
    assert client.post("/api/stop").status_code == 503
