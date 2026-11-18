"""Sequential crew orchestration (Phase 6 / v0.1)."""

from __future__ import annotations

from dataclasses import dataclass

from squad.crew.flagged import flagged_files
from squad.crew.gates import evaluate_gates, gates_all_pass
from squad.crew.roster import AgentSpec
from squad.report.run_report import build_run_report


@dataclass
class RunResult:
    ok: bool
    approved: bool
    message: str
    report: dict


def run_sequential(
    task: str,
    crew: list[AgentSpec],
    *,
    plan_provider,
    approver,
    coder_runner,
    prev_metrics: dict,
    curr_metrics: dict,
    findings: list[dict],
    changed_files: list[str],
    cost_per_agent: dict,
    not_checked: list[str],
) -> RunResult:
    plan = plan_provider(task)
    if not approver(plan):
        return RunResult(False, False, "plan not approved", {"plan": plan})

    agent_result = coder_runner(task)

    gates = evaluate_gates(prev_metrics, curr_metrics, findings)
    flagged = flagged_files(changed_files)

    report = build_run_report(
        task=task,
        crew=[a.name for a in crew],
        plan=plan,
        agent_ok=agent_result.ok,
        agent_message=agent_result.message,
        gates=gates,
        flagged=flagged,
        changed_files=changed_files,
        cost_per_agent=cost_per_agent,
        not_checked=not_checked,
    )
    ok = agent_result.ok and gates_all_pass(gates)
    return RunResult(ok, True, "done" if ok else "agent or gates failed", report)
