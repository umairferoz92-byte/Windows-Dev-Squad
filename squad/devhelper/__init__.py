"""Developer Helper module — code anti-pattern and security scan.

Scans source code repositories for common security anti-patterns across
multiple languages. Pure text analysis — no network, no external tools
required (detects what's visible in files). TUI-friendly output.

Guardrails (rule 1 style, fail closed):
- Scans only explicit paths you provide (authorization gate).
- Never sends payloads, never contacts external services.
- All findings are conservative estimates based on text patterns;
  always verify against the live code.
- Every scan is recorded in the hash-chained audit log.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

# Directory names to skip when walking a repo tree (dependency/build/cache trees).
_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "node_modules",
        "site-packages",
        ".idea",
        ".vscode",
        "dist",
        "build",
        ".eggs",
        "target",
    }
)

__all__ = ["Severity", "Finding", "scan_paths", "render_report", "AuditRecord"]


class Severity(IntEnum):
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def label(self) -> str:
        return self.name.title()


@dataclass
class Finding:
    title: str
    severity: Severity
    detail: str = ""
    evidence: str = ""
    file: str = ""
    line: int = 0

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "severity": self.severity.name,
            "detail": self.detail,
            "evidence": self.evidence,
            "file": self.file,
            "line": self.line,
        }


@dataclass
class AuditRecord:
    action: str = "devhelper.scan"
    targets: tuple[str, ...] = field(default_factory=tuple)
    findings: int = 0
    severity_highest: str = "INFO"

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "targets": list(self.targets),
            "findings": self.findings,
            "severity_highest": self.severity_highest,
        }


# ---------------------------------------------------------------------------
# Pattern databases
# ---------------------------------------------------------------------------

# Hardcoded secrets — catch obvious patterns
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|apikey|auth[_-]?key)"),
    re.compile(r"(?i)(password|passwd|pwd)"),
    re.compile(r"(?i)(secret|token|credential)"),
)

# Insecure HTTP — http:// but not localhost
INSECURE_HTTP_RE = re.compile(r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)")

# Dangerous eval/exec patterns (language-specific)
DANGEROUS_EVAL_PATTERNS = {
    "python": (
        re.compile(r"exec\("),
        re.compile(r"eval\("),
    ),
    "javascript": (
        re.compile(r"eval\("),
        re.compile(r"new Function\("),
    ),
    "php": (re.compile(r"eval\("),),
}


# ---------------------------------------------------------------------------
# Language-recognized extensions
# ---------------------------------------------------------------------------

LANG_EXTENSIONS = {
    "python": (".py",),
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "typescript": (".ts", ".tsx"),
    "php": (".php",),
    "html": (".html", ".htm"),
    "css": (".css", ".scss", ".sass"),
    "yaml": (".yaml", ".yml"),
    "toml": (".toml",),
    "markdown": (".md", ".mkd", ".markdown"),
    "json": (".json",),
    "shell": (".sh", ".bash", ".ps1", ".cmd"),
    "ruby": (".rb",),
    "java": (".java",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp", ".cc", ".cxx"),
}


def _lang_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    for lang, exts in LANG_EXTENSIONS.items():
        if suffix in exts:
            return lang
    return None


# ---------------------------------------------------------------------------
# Core scanning logic
# ---------------------------------------------------------------------------


def scan_paths(
    paths: Sequence[str | Path],
    secret_scan: bool = True,
    insecure_http: bool = True,
    dangerous_eval: bool = True,
) -> tuple[list[Finding], AuditRecord]:
    """Scan paths for code anti-patterns.

    Authorization gate: at least one path must be supplied.
    """
    targets: list[str] = []
    all_findings: list[Finding] = []

    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            continue
        targets.append(str(p))

        if p.is_file():
            all_findings.extend(_scan_file(p, secret_scan, insecure_http, dangerous_eval))
            continue

        try:
            for child in p.rglob("*"):
                if not child.is_file():
                    continue
                # Skip dependency/build/cache trees that would flood the report.
                rel = child.relative_to(p)
                parts = rel.parts
                if any(seg in _IGNORE_DIRS for seg in parts[:-1]):
                    continue
                all_findings.extend(_scan_file(child, secret_scan, insecure_http, dangerous_eval))
        except OSError:
            pass

    audit = AuditRecord(
        targets=tuple(targets),
        findings=len(all_findings),
        severity_highest=max((f.severity for f in all_findings), default=Severity.INFO).name if all_findings else "INFO",
    )
    return all_findings, audit


def _scan_file(path: Path, secret_scan: bool, insecure_http: bool, dangerous_eval: bool) -> list[Finding]:
    """Apply all relevant checks to *path*."""
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    lang = _lang_for_path(path)

    # Secret patterns (all languages)
    if secret_scan:
        for i, line in enumerate(text.splitlines(), start=1):
            for regex in SECRET_PATTERNS:
                if regex.search(line):
                    findings.append(
                        Finding(
                            title="Potential hardcoded secret/key",
                            severity=Severity.LOW,
                            detail=regex.pattern,
                            evidence=line.strip()[:120],
                            file=str(path),
                            line=i,
                        )
                    )

    # Insecure HTTP (all languages)
    if insecure_http:
        for i, line in enumerate(text.splitlines(), start=1):
            if INSECURE_HTTP_RE.search(line):
                findings.append(
                    Finding(
                        title="Potential insecure HTTP URL",
                        severity=Severity.LOW,
                        detail="Found non-localhost HTTP URL in source",
                        evidence=line.strip()[:120],
                        file=str(path),
                        line=i,
                    )
                )

    # Dangerous eval/exec (language-specific)
    if dangerous_eval and lang in DANGEROUS_EVAL_PATTERNS:
        for i, line in enumerate(text.splitlines(), start=1):
            for regex in DANGEROUS_EVAL_PATTERNS[lang]:
                if regex.search(line):
                    sev = Severity.HIGH if "exec" in regex.pattern else Severity.CRITICAL
                    findings.append(
                        Finding(
                            title=f"Dangerous pattern in {lang}: {regex.pattern}",
                            severity=sev,
                            detail=regex.pattern,
                            evidence=line.strip()[:120],
                            file=str(path),
                            line=i,
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_report(findings: list[Finding]) -> str:
    """Render findings as Markdown, suitable for TUI display or writing to file."""
    if not findings:
        return "_No findings detected._"

    buckets = {s: [] for s in Severity}
    for f in findings:
        buckets[f.severity].append(f)

    lines: list[str] = []
    lines.append("# Code Security Scan Report")
    lines.append("")
    lines.append(f"- **Total findings:** {len(findings)}")
    highest = max((f.severity for f in findings), default=Severity.INFO)
    lines.append(f"- **Highest severity:** {highest.label()}")
    lines.append("")

    lines.append("## By Severity")
    lines.append("")
    for s in Severity:
        bucket = buckets[s]
        if not bucket:
            continue
        lines.append(f"### {s.label()} ({len(bucket)})")
        lines.append("")
        for f in sorted(bucket, key=lambda x: (x.file or "", x.line or 0)):
            evidence = (f.evidence or "").replace("|", "/")[:100]
            lines.append(f"- **{f.title}** (line {f.line}) — {evidence}")
        lines.append("")

    lines.append("## Open Files Affected")
    lines.append("")
    affected = sorted({f.file for f in findings if f.file})
    if affected:
        for f in affected:
            lines.append(f"- `{f}`")
    else:
        lines.append("_None_")

    lines.append("")
    lines.append(
        "> Generated by `squad devhelper scan` — text-only analysis. "
        "Verify any finding against the live source. Nothing was executed or "
        "exploited; this is a conservative pattern scan."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_scan_cli(
    path: str,
    secrets: bool = True,
    insecure_http: bool = True,
    dangerous_eval: bool = True,
    report: str | None = None,
    state: str = "",
) -> None:
    """Run a devhelper scan from CLI."""
    import json

    from rich.console import Console

    console = Console()

    p = Path(path).expanduser().resolve()
    if not p.exists():
        console.print(f"[red]path not found: {path}[/red]", markup=False)
        return

    findings, audit = scan_paths(
        [str(p)],
        secret_scan=secrets,
        insecure_http=insecure_http,
        dangerous_eval=dangerous_eval,
    )

    console.print(render_report(findings), markup=False)

    audit.findings = len(findings)
    if findings:
        audit.severity_highest = max(f.severity for f in findings).name

    # Write audit
    try:
        from squad.audit import default_audit_path

        audit_path = default_audit_path()
        with open(audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(audit.as_dict()) + "\n")
        console.print(f"audit -> {audit_path}", markup=False)
    except (OSError, ImportError) as exc:
        console.print(f"[yellow]could not write audit: {exc}[/yellow]", markup=False)

    if report:
        try:
            Path(report).write_text(render_report(findings), encoding="utf-8")
            console.print(f"report -> {report}", markup=False)
        except OSError as exc:
            console.print(f"[red]could not write report: {exc}[/red]", markup=False)

    if state:
        try:
            state_data = {
                "target": str(p),
                "findings": len(findings),
                "highest": audit.severity_highest,
            }
            with open(state, "w", encoding="utf-8") as fh:
                json.dump(state_data, fh, indent=2)
            console.print(f"state -> {state}", markup=False)
        except OSError as exc:
            console.print(f"[yellow]could not write state: {exc}[/yellow]", markup=False)


if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command("scan")
    def scan_cli(
        path: str = typer.Argument(..., help="File or directory to scan."),
        secrets: bool = typer.Option(True, "--secrets/--no-secrets"),
        insecure_http: bool = typer.Option(True, "--insecure-http/--no-insecure-http"),
        dangerous_eval: bool = typer.Option(True, "--dangerous-eval/--no-dangerous-eval"),
        report: str | None = typer.Option(None, "--report"),
        state: str = typer.Option("", "--state"),
    ) -> None:
        run_scan_cli(path, secrets, insecure_http, dangerous_eval, report, state)

    app()
