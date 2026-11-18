"""Tests for the guard's default-deny decision logic and tool tiers."""

from squad.guard import DEFAULT_POLICY, Policy, ToolRequest, Verdict, evaluate


def _policy(**overrides):
    return Policy({**DEFAULT_POLICY, **overrides})


def test_partial_policy_keeps_default_tools():
    policy = Policy({"write_scope": ["/repo/src"]})
    assert policy.data["write_scope"] == ["/repo/src"]
    assert policy.data["tools"]["read_file"]["tier"] == 0


def test_unknown_tool_defaults_to_ask():
    request = ToolRequest(tool="mystery_tool", args={}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.ASK


def test_read_file_tier0_allowed():
    request = ToolRequest(tool="read_file", args={"path": "/repo/src/a.py"}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.ALLOW


def test_run_tests_without_isolation_asks():
    request = ToolRequest(tool="run_tests", args={}, cwd="/repo", isolation_level=None)
    assert evaluate(request, _policy()).verdict is Verdict.ASK


def test_run_tests_with_isolation_allowed():
    request = ToolRequest(tool="run_tests", args={}, cwd="/repo", isolation_level=2)
    assert evaluate(request, _policy()).verdict is Verdict.ALLOW


def test_edit_file_in_scope_allowed():
    request = ToolRequest(tool="edit_file", args={"path": "/repo/src/a.py"}, cwd="/repo")
    assert evaluate(request, _policy(write_scope=["/repo/src"])).verdict is Verdict.ALLOW


def test_edit_file_outside_scope_asks():
    request = ToolRequest(tool="edit_file", args={"path": "/etc/passwd"}, cwd="/repo")
    assert evaluate(request, _policy(write_scope=["/repo/src"])).verdict is Verdict.ASK


def test_edit_file_dot_git_asks():
    request = ToolRequest(tool="edit_file", args={"path": "/repo/src/.git/config"}, cwd="/repo")
    assert evaluate(request, _policy(write_scope=["/repo/src"])).verdict is Verdict.ASK


def test_edit_file_credential_location_denied():
    request = ToolRequest(tool="edit_file", args={"path": "/home/u/.ssh/id_rsa"}, cwd="/repo")
    decision = evaluate(request, _policy(write_scope=["/home/u"]))
    assert decision.verdict is Verdict.DENY


def test_edit_file_blocked_absolute_denied(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    request = ToolRequest(tool="edit_file", args={"path": str(blocked / "x.txt")}, cwd="/repo")
    decision = evaluate(request, _policy(write_scope=["/repo/src"], blocked_paths=[str(blocked)]))
    assert decision.verdict is Verdict.DENY


def test_edit_file_missing_path_denied():
    request = ToolRequest(tool="edit_file", args={}, cwd="/repo")
    assert evaluate(request, _policy(write_scope=["/repo/src"])).verdict is Verdict.DENY


def test_edit_file_sensitive_config_denied():
    request = ToolRequest(tool="edit_file", args={"path": "/repo/squad.yaml"}, cwd="/repo")
    decision = evaluate(
        request,
        _policy(write_scope=["/repo"], sensitive_files=["squad.yaml", "guard.yaml", "prices.yaml"]),
    )
    assert decision.verdict is Verdict.DENY


def test_edit_file_ci_workflow_asks():
    request = ToolRequest(
        tool="edit_file", args={"path": "/repo/.github/workflows/ci.yml"}, cwd="/repo"
    )
    decision = evaluate(request, _policy(write_scope=["/repo"], sensitive_dirs=[".github"]))
    assert decision.verdict is Verdict.ASK


def test_edit_file_traversal_asks():
    request = ToolRequest(
        tool="edit_file", args={"path": "/repo/src/../../etc/passwd"}, cwd="/repo"
    )
    assert evaluate(request, _policy(write_scope=["/repo/src"])).verdict is Verdict.ASK


def test_install_dependencies_tier2_asks():
    request = ToolRequest(tool="install_dependencies", args={"package": "requests"}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.ASK


def test_git_push_tier3_denied():
    request = ToolRequest(tool="git_push", args={}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.DENY


def test_raw_shell_denied():
    request = ToolRequest(tool="raw_shell", args={"command": "echo hi"}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.DENY


def test_credential_access_denied():
    request = ToolRequest(tool="credential_access", args={}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.DENY


def test_invoke_squad_denied():
    request = ToolRequest(tool="invoke_squad", args={}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.DENY


def test_admin_elevation_denied():
    request = ToolRequest(tool="admin_elevation", args={}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.DENY


def test_git_commit_tier1_allowed():
    request = ToolRequest(tool="git_commit", args={"message": "fix bug"}, cwd="/repo")
    assert evaluate(request, _policy()).verdict is Verdict.ALLOW


def test_destructive_command_arg_denied():
    policy = _policy()
    policy.data["tools"]["custom_scan"] = {"tier": 0}
    request = ToolRequest(tool="custom_scan", args={"command": "rm -rf /"}, cwd="/repo")
    assert evaluate(request, policy).verdict is Verdict.DENY
