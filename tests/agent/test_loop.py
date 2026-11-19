"""Tests for the single agent loop (scripted provider, offline)."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from squad.agent import Agent, LoopDetectedError
from squad.budget import BudgetError, BudgetLimits, BudgetManager, PriceTable
from squad.guard import Policy
from squad.providers.base import ChatResponse

PRACTICE_DIR = Path(__file__).resolve().parents[2] / "practice"


class ScriptedProvider:
    name = "scripted"

    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, model, messages, max_tokens=1024):
        text = self.responses.pop(0) if self.responses else '{"action": "final", "args": {"message": "done"}}'
        return ChatResponse(text=text, usage=None, model=model)


class RecordingProvider:
    name = "scripted"

    def __init__(self):
        self.calls = 0

    def chat(self, model, messages, max_tokens=1024):
        self.calls += 1
        return ChatResponse(text='{"action": "final"}', usage=None, model=model)


def _budget(per_agent=1.0):
    prices = PriceTable({"models": {"scripted/model": {"input": 0.0, "output": 0.0}}})
    return BudgetManager(BudgetLimits(per_agent=per_agent), prices)


def _agent(provider, cwd, write_scope=None, test_command=None, budget=None, **kw):
    scope = write_scope or [str(cwd)]
    return Agent(
        name="coder",
        role="worker",
        model="scripted/model",
        provider=provider,
        budget=budget or _budget(),
        policy=Policy({"write_scope": scope}),
        cwd=str(cwd),
        test_command=test_command,
        **kw,
    )


def test_agent_fixes_practice_repo(tmp_path):
    repo = tmp_path / "practice"
    shutil.copytree(PRACTICE_DIR, repo)
    fixed = '"""Practice target project (throwaway)."""\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n'
    provider = ScriptedProvider(
        [
            json.dumps({"action": "edit_file", "args": {"path": str(repo / "app.py"), "content": fixed}}),
            json.dumps({"action": "final", "args": {"message": "done"}}),
        ]
    )
    agent = _agent(provider, repo, test_command=[sys.executable, "-m", "pytest", "-q"])
    result = agent.run("fix the failing test")
    assert result.ok is True
    assert "return a + b" in (repo / "app.py").read_text(encoding="utf-8")


def test_agent_loop_detection(tmp_path):
    action = json.dumps({"action": "edit_file", "args": {"path": str(tmp_path / "a.py"), "content": "x"}})
    provider = ScriptedProvider([action, action])
    agent = _agent(provider, tmp_path)
    with pytest.raises(LoopDetectedError):
        agent.run("task")


def test_agent_step_limit(tmp_path):
    class Stepper:
        name = "scripted"

        def __init__(self, cwd):
            self.cwd = str(cwd)
            self.i = 0

        def chat(self, model, messages, max_tokens=1024):
            self.i += 1
            return ChatResponse(
                text=json.dumps(
                    {
                        "action": "edit_file",
                        "args": {"path": self.cwd + "/x.py", "content": f"v{self.i}"},
                    }
                ),
                usage=None,
                model=model,
            )

    agent = _agent(Stepper(tmp_path), tmp_path, max_steps=3)
    result = agent.run("task")
    assert result.ok is False
    assert result.steps == 3
    assert "step limit" in result.message


def test_agent_guard_denies_outside_scope(tmp_path):
    scope = tmp_path / "scope"
    scope.mkdir()
    outside = tmp_path / "outside.txt"
    provider = ScriptedProvider([json.dumps({"action": "edit_file", "args": {"path": str(outside), "content": "x"}})])
    agent = _agent(provider, tmp_path, write_scope=[str(scope)])
    result = agent.run("edit outside")
    assert result.ok is False
    assert "outside the configured write scope" in result.message


def test_agent_budget_refuses_before_send(tmp_path):
    provider = RecordingProvider()
    budget = BudgetManager(
        BudgetLimits(per_call_input_tokens=1),
        PriceTable({"models": {"scripted/model": {"input": 0.0, "output": 0.0}}}),
    )
    agent = _agent(provider, tmp_path, budget=budget)
    with pytest.raises(BudgetError):
        agent.run("task that produces a long prompt")
    assert provider.calls == 0  # refused before any model call was sent


def test_agent_audits_actions(tmp_path):
    from squad.audit import AuditLog

    audit = AuditLog(str(tmp_path / "audit.jsonl"))
    provider = ScriptedProvider(
        [
            json.dumps({"action": "edit_file", "args": {"path": str(tmp_path / "a.py"), "content": "x"}}),
            json.dumps({"action": "final", "args": {"message": "done"}}),
        ]
    )
    agent = _agent(provider, tmp_path, audit=audit)
    result = agent.run("task")
    assert result.ok is True
    assert audit.verify() is True
    assert audit.latest_hash  # entries were appended
    events = [entry["event"] for entry in audit._entries]
    assert "tool_call" in events
    assert "final" in events
