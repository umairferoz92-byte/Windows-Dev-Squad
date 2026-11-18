"""Single agent loop: step limit, loop detection, guard validation, verification-gated done."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from squad.agent.actions import parse_action
from squad.audit import AuditLog
from squad.budget import BudgetManager, estimate_tokens
from squad.exec import run_command
from squad.guard import Policy, ToolRequest, Verdict, evaluate
from squad.providers.base import Provider

FINAL = "final"
DEFAULT_MAX_STEPS = 12


class LoopDetectedError(RuntimeError):
    pass


@dataclass
class AgentResult:
    ok: bool
    steps: int
    message: str
    history: list = field(default_factory=list)


@dataclass
class Agent:
    name: str
    role: str
    model: str
    provider: Provider
    budget: BudgetManager
    policy: Policy
    cwd: str
    write_scope: list = field(default_factory=list)
    test_command: list | None = None
    max_steps: int = DEFAULT_MAX_STEPS
    max_output_tokens: int = 2048
    approver: Callable | None = None
    audit: AuditLog | None = None

    def run(self, task: str) -> AgentResult:
        history: list = []
        seen: set = set()
        for step in range(1, self.max_steps + 1):
            prompt = self._build_prompt(task, history)
            in_tokens = estimate_tokens(prompt)
            estimate = self.budget.preflight(
                self.name, self.provider.name, self.model, in_tokens, self.max_output_tokens
            )
            resp = self.provider.chat(
                self.model, [{"role": "user", "content": prompt}], max_tokens=self.max_output_tokens
            )
            self.budget.record(
                estimate,
                self.name,
                self.provider.name,
                tokens_in=in_tokens,
                tokens_out=estimate_tokens(resp.text),
            )

            action = parse_action(resp.text)
            name = action["action"]
            args = action.get("args") or {}

            if name == FINAL:
                ok = self._verify()
                self._audit("final", ok=ok)
                if ok:
                    return AgentResult(True, step, args.get("message", "done"), history)
                return AgentResult(False, step, "verification failed after final", history)

            key = (name, json.dumps(args, sort_keys=True))
            if key in seen:
                raise LoopDetectedError(f"loop detected: repeated '{name}'")
            seen.add(key)

            decision = evaluate(ToolRequest(tool=name, args=args, cwd=self.cwd), self.policy)
            if decision.verdict is Verdict.ALLOW:
                self._audit("tool_call", tool=name, args=args, verdict="allow")
                self._execute(name, args)
            elif decision.verdict is Verdict.ASK:
                if self.approver is not None and self.approver(decision, name, args):
                    self._audit("tool_call", tool=name, args=args, verdict="approved")
                    self._execute(name, args)
                else:
                    history.append({"step": step, "action": name, "denied": decision.reason})
                    self._audit("tool_denied", tool=name, reason=decision.reason)
                    return AgentResult(False, step, f"denied: {decision.reason}", history)
            else:
                history.append({"step": step, "action": name, "denied": decision.reason})
                self._audit("tool_denied", tool=name, reason=decision.reason)
                return AgentResult(False, step, f"blocked: {decision.reason}", history)

            history.append({"step": step, "action": name, "args": args})

        return AgentResult(False, self.max_steps, "step limit reached without final", history)

    def _build_prompt(self, task: str, history: list) -> str:
        return json.dumps({"task": task, "recent": history[-4:]})

    def _audit(self, event: str, **fields) -> None:
        if self.audit is not None:
            self.audit.append(event, agent=self.name, role=self.role, **fields)

    def _verify(self) -> bool:
        if not self.test_command:
            return True
        result = run_command(
            list(self.test_command), cwd=self.cwd, isolation_level=0, is_agent_code=False
        )
        return result.returncode == 0

    def _execute(self, name: str, args: dict) -> None:
        if name == "edit_file":
            path = args.get("path")
            content = args.get("content", "")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        elif name == "run_tests" and self.test_command:
            run_command(
                list(self.test_command), cwd=self.cwd, isolation_level=0, is_agent_code=False
            )
