"""Build and render the `squad check` report."""

from __future__ import annotations

from squad.checks.check import CHECK_TOOLS


def build_report(results, cwd: str, isolation_level: int = 0) -> dict:
    done_names = {r.name for r in results}
    not_checked = [name for name in CHECK_TOOLS if name not in done_names]
    passed = [r for r in results if r.passed]
    failed = [r for r in results if r.verdict == "allow" and not r.passed]
    denied = [r for r in results if r.verdict != "allow"]
    return {
        "repo": cwd,
        "isolation_level": isolation_level,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "denied": len(denied),
        },
        "not_checked": not_checked,
    }


def render_report(report: dict) -> str:
    lines = [
        "squad check report",
        "=" * 40,
        f"repo: {report['repo']}",
        f"isolation: level {report['isolation_level']} (own account — trusted repos only)",
        "",
    ]
    for r in report["results"]:
        if r.verdict != "allow":
            status = "DENY"
        elif r.passed:
            status = "PASS"
        else:
            status = "FAIL"
        code = f"exit {r.returncode}" if r.returncode is not None else "not run"
        lines.append(f"[{status:4}] {r.name:14} ({code}) {' '.join(r.command)}")
        if status == "FAIL":
            for line in r.stdout.strip().splitlines()[-5:]:
                lines.append("       " + line)
    lines.append("")
    s = report["summary"]
    lines.append(f"Summary: {s['passed']} passed, {s['failed']} failed, {s['denied']} denied")
    if report["not_checked"]:
        lines.append("Not checked: " + ", ".join(report["not_checked"]) + " (not configured)")
    return "\n".join(lines) + "\n"
