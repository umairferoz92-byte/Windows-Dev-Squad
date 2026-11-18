"""Oracle: the report writer (Prompt 5).

Oracle takes the JSON findings from Nightwing's phases and produces a report:
  - executive summary (what was tested, what was skipped and why, risk picture)
  - findings table sorted by severity, with CWE and OWASP Top 10 mapping
  - a "what was skipped and why" section (tools not installed, declined phases)
  - a raw-evidence appendix

Oracle MUST NOT change a severity or drop a finding Nightwing produced. It may
only de-duplicate exact repeats and format. Evidence snippets are redacted of
secret-looking strings (API keys, passwords) before they reach the report.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from squad.security_findings import SecurityFinding, SecuritySeverity

# Severity ordering for the findings table (highest first).
_SEVERITY_ORDER = [
    SecuritySeverity.CRITICAL,
    SecuritySeverity.HIGH,
    SecuritySeverity.MEDIUM,
    SecuritySeverity.LOW,
    SecuritySeverity.INFO,
]

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
_SECRET_PATTERNS = [
    # Bearer / Basic tokens
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/]+={0,2}"),
    # Common AWS / generic secret keys
    re.compile(r"(?i)\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[^\s'\"&]{6,}"),
    re.compile(r"(?i)password\s*[=:]\s*\S+"),
    # Generic long base64-ish blobs
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
]

_REDACTED = "[REDACTED]"


def redact_evidence(text: str) -> str:
    """Remove secret-looking strings from an evidence snippet."""
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


def _finding_key(f: SecurityFinding) -> str:
    """Dedupe key: exact repeats only. Tool+endpoint+severity+description."""
    return "|".join([
        f.tool,
        f.file_or_endpoint,
        f.severity.value,
        f.description,
    ])


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------
class Oracle:
    def __init__(
        self,
        findings: Optional[Iterable[SecurityFinding]] = None,
        target: str = "",
        skipped: Optional[dict] = None,
    ):
        # Dedupe exact repeats immediately on ingest; never alter severity.
        seen: dict[str, SecurityFinding] = {}
        for f in findings or []:
            seen.setdefault(_finding_key(f), f)
        self.findings: list[SecurityFinding] = list(seen.values())
        self.target = target
        self.skipped = skipped or {}

    # -- aggregation --------------------------------------------------------
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sev in _SEVERITY_ORDER:
            counts[sev.value] = 0
        for f in self.findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        return counts

    def sorted_findings(self) -> list[SecurityFinding]:
        order = {s.value: i for i, s in enumerate(_SEVERITY_ORDER)}
        return sorted(self.findings, key=lambda f: order.get(f.severity.value, 99))

    def overall_risk(self) -> str:
        counts = self.by_severity()
        if counts.get("critical", 0):
            return "Critical"
        if counts.get("high", 0):
            return "High"
        if counts.get("medium", 0):
            return "Medium"
        if counts.get("low", 0):
            return "Low"
        return "No significant findings"

    # -- executive summary --------------------------------------------------
    def _executive_summary(self) -> str:
        counts = self.by_severity()
        tested = len(self.findings)
        skipped_note = (
            "No tools or phases were skipped."
            if not self.skipped
            else "Some tools/phases were skipped; see the coverage note below."
        )
        return (
            "## Executive Summary\n\n"
            f"**Target:** `{self.target or '(not specified)'}`\n\n"
            f"Oracle aggregated **{tested}** finding(s) produced by Nightwing. "
            f"Overall risk picture: **{self.overall_risk()}**.\n\n"
            f"| Severity | Count |\n"
            f"|----------|-------|\n"
        ) + "".join(
            f"| {sev.upper()} | {counts.get(sev, 0)} |\n" for sev in ("critical", "high", "medium", "low", "info")
        ) + (
            f"\nWhat was tested and what was skipped: {skipped_note}\n"
        )

    # -- findings table -----------------------------------------------------
    def _findings_table(self) -> str:
        rows = self.sorted_findings()
        if not rows:
            return "## Findings\n\nNo findings were reported.\n"
        lines = [
            "## Findings\n",
            "| Severity | Tool | CWE | OWASP Top 10 | Affected | Description |",
            "|----------|------|-----|--------------|----------|-------------|",
        ]
        for f in rows:
            cwe = f.cwe or "-"
            owasp = f.owasp_category or "-"
            affected = f.file_or_endpoint.replace("|", "\\|")
            desc = f.description.replace("|", "\\|")
            lines.append(
                f"| {f.severity.value.upper()} | {f.tool} | {cwe} | {owasp} | "
                f"`{affected}` | {desc} |"
            )
        return "\n".join(lines) + "\n"

    # -- coverage / skipped ------------------------------------------------
    def _coverage_note(self) -> str:
        if not self.skipped:
            return "## Coverage\n\nNo tools or phases were skipped.\n"
        lines = ["## Coverage: what was skipped and why\n"]
        for key, reason in self.skipped.items():
            lines.append(f"- **{key}** — skipped: {reason}")
        return "\n".join(lines) + "\n"

    # -- raw evidence appendix ---------------------------------------------
    def _raw_evidence(self) -> str:
        rows = self.sorted_findings()
        if not rows:
            return "## Raw Evidence Appendix\n\n(no evidence)\n"
        lines = ["## Raw Evidence Appendix\n"]
        for i, f in enumerate(rows, 1):
            lines.append(f"### {i}. {f.tool} — {f.severity.value.upper()}")
            lines.append(f"**Affected:** `{f.file_or_endpoint}`")
            if f.description:
                lines.append(f"**Description:** {f.description}")
            if f.remediation:
                lines.append(f"**Remediation:** {f.remediation}")
            ev = redact_evidence(f.evidence_snippet)
            lines.append("```text")
            lines.append(ev or "(no evidence snippet)")
            lines.append("```")
            lines.append("")
        return "\n".join(lines) + "\n"

    # -- compliance mapping ------------------------------------------------
    def _compliance_section(self) -> str:
        from squad.compliance import summary_controls

        controls = summary_controls(self.findings)
        if not any(controls.values()):
            return "## Compliance Mapping\n\nNo OWASP categories present to map.\n"
        lines = ["## Compliance Mapping\n"]
        lines.append("Findings map to the following controls (best-effort from OWASP category):\n")
        for frame, name in (("nist", "NIST 800-53"), ("iso", "ISO 27001"), ("pci", "PCI DSS")):
            vals = controls[frame]
            lines.append(f"- **{name}**: {', '.join(vals) if vals else '(none)'}")
        return "\n".join(lines) + "\n"

    # -- report rendering ---------------------------------------------------
    def to_markdown(self) -> str:
        header = (
            "# Security Squad Report\n\n"
            f"_Generated {datetime.now(timezone.utc).isoformat()} by Oracle._\n\n"
        )
        return (
            header
            + self._executive_summary()
            + "\n"
            + self._findings_table()
            + "\n"
            + self._coverage_note()
            + "\n"
            + self._compliance_section()
            + "\n"
            + self._raw_evidence()
        )

    def to_html(self) -> str:
        """Optional HTML rendering (plain, self-contained)."""
        import html as _html

        md = self.to_markdown()
        safe = _html.escape(md)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Security Squad Report</title>"
            "<style>body{font-family:system-ui,sans-serif;margin:2em;"
            "max-width:900px;}pre{background:#f5f5f5;padding:1em;"
            "overflow:auto;}</style></head><body>"
            + safe.replace("\n", "<br>")
            + "</body></html>"
        )

    def to_pdf(self) -> bytes:
        """Render to a minimal single-page PDF (ReportLab-free, self-contained).

        Falls back to a text-based PDF when no HTML->PDF converter is available.
        """
        md = self.to_markdown()
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
        except ImportError:
            # Minimal hand-rolled PDF so PDF export always works.
            return _plain_pdf(md)

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        x, y = 50, height - 50
        c.setFont("Courier", 9)
        for line in md.splitlines():
            if y < 40:
                c.showPage()
                c.setFont("Courier", 9)
                y = height - 50
            # crude escape: reportlab fails on some chars
            safe = "".join(ch if ord(ch) < 128 else "?" for ch in line)
            c.drawString(x, y, safe[:110])
            y -= 12
        c.save()
        return buf.getvalue()

    def to_json(self) -> str:
        return json.dumps(
            {"target": self.target,
             "skipped": self.skipped,
             "findings": [f.to_dict() for f in self.sorted_findings()]},
            indent=2,
        )


def findings_from_json(payload: str | dict) -> list[SecurityFinding]:
    """Rebuild SecurityFinding objects from Nightwing's JSON output."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    return [SecurityFinding(**item) for item in data]


def _plain_pdf(md: str) -> bytes:
    """Minimal hand-rolled PDF so PDF export works without reportlab."""
    lines = md.splitlines()
    content = "BT\n/F1 9 Tf\n50 780 Td\n16 TL\n" + "".join(
        f"({_pdf_escape(l[:110])}) Tj\nT*\n" for l in lines
    ) + "ET\n"
    objects = (
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        "4 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n"
    ) % (len(content), content)
    chunks = [b"%PDF-1.4\n"]
    obj_texts = [t for t in objects.split("endobj\n") if t.strip()] + ["endobj\n"]
    offsets = [0]
    for t in obj_texts:
        chunks.append(t.encode("latin-1", "replace") + b"\n")
        offsets.append(offsets[-1] + len(chunks[-1]))
    total = b"".join(chunks)
    n = len(obj_texts)
    xref = b"xref\n0 %d\n" % (n + 1)
    xref += b"0000000000 65535 f \n"
    for o in offsets[1:n + 1]:
        xref += ("%010d 00000 n \n" % o).encode("latin-1")
    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (n + 1, len(total) + len(xref))
    return total + xref + trailer


def _pdf_escape(s: str) -> str:
    out = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return "".join(ch if ord(ch) < 128 else "?" for ch in out)