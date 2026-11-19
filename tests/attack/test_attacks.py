"""Attack tests against the guard, budget layer, and agents.

Prompt injection, secret leaks, guard bypass, self-approval, budget bypass, and
escalation by names. Each test asserts the security property HOLDS; if any fails
we fix the vulnerability, never the test.
"""

import json
import sys

import pytest

from squad.agent import Agent
from squad.budget import BudgetError, BudgetLimits, BudgetManager, PriceTable
from squad.crew import assemble_crew
from squad.exec import run_command
from squad.guard import ApprovalStore, Policy, ToolRequest, Verdict, evaluate
from squad.providers.base import ChatResponse


class ScriptedProvider:
    name = "scripted"

    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, model, messages, max_tokens=1024):
        text = self.responses.pop(0) if self.responses else '{"action": "final", "args": {"message": "done"}}'
        return ChatResponse(text=text, usage=None, model=model)


def _agent(provider, cwd, **kw):
    kw.setdefault("policy", Policy({"write_scope": [str(cwd)]}))
    return Agent(
        name="coder",
        role="worker",
        model="m",
        provider=provider,
        budget=BudgetManager(
            BudgetLimits(per_agent=1.0),
            PriceTable({"models": {"m": {"input": 0.0, "output": 0.0}}}),
        ),
        cwd=str(cwd),
        **kw,
    )


# --- prompt injection --------------------------------------------------------


def test_prompt_injection_blocked_tool_is_denied(tmp_path):
    provider = ScriptedProvider(['{"action": "raw_shell", "args": {"command": "rm -rf /"}}'])
    result = _agent(provider, tmp_path).run("task")
    assert result.ok is False
    assert "blocked" in result.message


def test_prompt_injection_unknown_action_default_deny(tmp_path):
    provider = ScriptedProvider(['{"action": "delete_production_db", "args": {}}'])
    result = _agent(provider, tmp_path).run("task")
    assert result.ok is False
    assert "denied" in result.message or "blocked" in result.message


def test_prompt_injection_out_of_scope_edit_denied(tmp_path):
    outside = tmp_path / "secret.txt"
    provider = ScriptedProvider([json.dumps({"action": "edit_file", "args": {"path": str(outside), "content": "exfil"}})])
    scope = tmp_path / "scope"
    scope.mkdir()
    agent = _agent(provider, tmp_path, policy=Policy({"write_scope": [str(scope)]}))
    result = agent.run("task")
    assert result.ok is False
    assert not outside.exists()


# --- secret leaks ------------------------------------------------------------


def test_secrets_not_leaked_to_subprocess(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-super-secret")
    result = run_command([sys.executable, "-c", "import os; print(os.environ.get('OPENROUTER_API_KEY',''))"])
    assert "sk-super-secret" not in result.stdout


# --- guard bypass ------------------------------------------------------------


def test_guard_bypass_encoded_traversal():
    policy = Policy({"write_scope": ["C:/repo/src"]})
    for path in (
        "C:/repo/src/%2e%2e/secret",
        "C:/repo/src/..%5c..%5csecret",
        "C:/repo/src/../secret",
    ):
        req = ToolRequest("edit_file", {"path": path}, "C:/repo")
        assert evaluate(req, policy).verdict is not Verdict.ALLOW


@pytest.mark.skipif(sys.platform != "win32", reason="Windows backslash traversal")
def test_guard_bypass_backslash_traversal_windows():
    policy = Policy({"write_scope": ["C:/repo/src"]})
    req = ToolRequest("edit_file", {"path": r"C:\repo\src\..\..\Windows\System32\config"}, "C:/repo")
    assert evaluate(req, policy).verdict is not Verdict.ALLOW


def test_guard_bypass_credential_location():
    policy = Policy({"blocked_components": [".ssh"]})
    req = ToolRequest("edit_file", {"path": "C:/home/u/.ssh/id_rsa"}, "C:/repo")
    assert evaluate(req, policy).verdict is Verdict.DENY


def test_guard_unknown_tool_cannot_escalate():
    policy = Policy()
    # A forged tool name that looks privileged is still default-deny.
    for tool in ("sudo", "admin_shell", "bypass", "debug_console"):
        assert evaluate(ToolRequest(tool, {}, "/repo"), policy).verdict is Verdict.ASK


# --- self-approval -----------------------------------------------------------


def test_agent_cannot_self_approve():
    store = ApprovalStore()
    with pytest.raises(ValueError):
        store.grant("ironman", "edit_file", "/repo", {"path": "/repo/a.py"})


# --- budget bypass -----------------------------------------------------------


def test_budget_cannot_be_bypassed_by_token_count():
    prices = PriceTable({"models": {"m": {"input": 1000.0, "output": 0.0}}})
    budget = BudgetManager(BudgetLimits(per_task=0.001), prices)
    with pytest.raises(BudgetError):
        budget.preflight("a", "openrouter", "m", 2, 0)  # 0.002 > 0.001


def test_budget_unknown_model_blocked():
    budget = BudgetManager(BudgetLimits(), PriceTable({"models": {}}))
    with pytest.raises(BudgetError):
        budget.preflight("a", "openrouter", "not-a-model", 1, 1)


# --- escalation by names -----------------------------------------------------


def test_privileged_name_gets_no_extra_permissions():
    policy = Policy()
    for actor_name in ("root", "administrator", "captain", "super"):
        req = ToolRequest("raw_shell", {"command": "whoami"}, "/repo", actor=actor_name)
        assert evaluate(req, policy).verdict is Verdict.DENY


def test_agent_name_does_not_grant_write_scope():
    crew = assemble_crew(1, names=["administrator"])
    assert crew[0].write_scope == "none"  # still the coordinator role
    crew = assemble_crew(2, names=["x", "administrator"])
    assert crew[1].role == "coder"  # name does not change the role's scope
