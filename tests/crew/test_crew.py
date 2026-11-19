"""Tests for sequential crew orchestration and the run report."""

from squad.agent import AgentResult
from squad.crew import assemble_crew, run_sequential
from squad.report.run_report import render_run_report


class _PlanProvider:
    def __call__(self, task):
        return f"plan for {task}"


class _Approver:
    def __init__(self, approve=True):
        self.approve_flag = approve

    def __call__(self, plan):
        return self.approve_flag


def _run(approver=True, curr=None, findings=None, changed=None, cost=None, not_checked=None):
    crew = assemble_crew(5)
    return run_sequential(
        "fix a bug",
        crew,
        plan_provider=_PlanProvider(),
        approver=_Approver(approver),
        coder_runner=lambda t: AgentResult(True, 1, "ok", []),
        prev_metrics={"tests_passed": 1, "tests_skipped": 0, "coverage": 0.0, "exit_code": 1},
        curr_metrics=curr or {"tests_passed": 1, "tests_skipped": 0, "coverage": 0.0, "exit_code": 0},
        findings=findings or [],
        changed_files=changed or ["src/main.py", "squad.yaml"],
        cost_per_agent=cost or {"coder": 0.001},
        not_checked=not_checked or ["typecheck"],
    )


def test_plan_not_approved_aborts():
    result = _run(approver=False)
    assert result.ok is False
    assert result.approved is False


def test_run_ok_and_report():
    result = _run()
    assert result.ok is True
    text = render_run_report(result.report)
    assert "flagged files" in text
    assert "squad.yaml" in text
    assert "not checked: typecheck" in text
    assert "cost per agent" in text


def test_run_fails_when_gate_fails():
    result = _run(findings=[{"severity": "high", "approved": False}])
    assert result.ok is False
