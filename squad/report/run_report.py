"""The one-page `squad run` report (diff, results, cost per agent, not-checked)."""

from __future__ import annotations


def build_run_report(
    *,
    task,
    crew,
    plan,
    agent_ok,
    agent_message,
    gates,
    flagged,
    changed_files,
    cost_per_agent,
    not_checked,
) -> dict:
    return {
        "task": task,
        "crew": crew,
        "plan": plan,
        "agent_ok": agent_ok,
        "agent_message": agent_message,
        "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail} for g in gates],
        "flagged": flagged,
        "changed_files": changed_files,
        "cost_per_agent": cost_per_agent,
        "not_checked": not_checked,
    }


def render_run_report(report: dict) -> str:
    lines = [
        "squad run report",
        "=" * 40,
        f"task: {report['task']}",
        f"crew: {', '.join(report['crew'])}",
        "",
        "plan: " + report["plan"][:200],
        "",
        "gates:",
    ]
    for g in report["gates"]:
        lines.append(f"  [{'PASS' if g['passed'] else 'FAIL'}] {g['name']}: {g['detail']}")
    lines.append("")
    lines.append("cost per agent:")
    for name, cost in report["cost_per_agent"].items():
        lines.append(f"  {name}: ${cost:.6f}")
    if report["flagged"]:
        lines.append("")
        lines.append("flagged files:")
        for entry in report["flagged"]:
            lines.append(f"  {entry['path']} -> {', '.join(entry['categories'])}")
    if report["changed_files"]:
        lines.append("")
        lines.append("changed files:")
        for p in report["changed_files"]:
            lines.append(f"  {p}")
    if report["not_checked"]:
        lines.append("")
        lines.append("not checked: " + ", ".join(report["not_checked"]))
    lines.append("")
    lines.append(f"result: {'ok' if report['agent_ok'] else 'failed'} ({report['agent_message']})")
    return "\n".join(lines) + "\n"
