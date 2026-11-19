"""Nightwing security finding models (Prompt 3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Evidence redaction. Lives here (leaf module) so the report writer, the
# SQLite store, and the export writers all share one implementation and no
# module needs to import the others (avoids cycles). Redaction is applied at
# the storage boundary so raw secrets never land in history.db or exports.
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
    """Remove secret-looking strings from an evidence snippet.

    Used before an evidence snippet is persisted to history.db or emitted in
    any export, so captured secrets (e.g. from gitleaks) do not survive at
    rest or in ticketing/audit output.
    """
    if not text:
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


class SecuritySeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    def label(self) -> str:
        colors = {
            "critical": "[bold red]CRITICAL[/bold red]",
            "high": "[red]HIGH[/red]",
            "medium": "[yellow]MEDIUM[/yellow]",
            "low": "[blue]LOW[/blue]",
            "info": "[cyan]INFO[/cyan]",
        }
        return colors.get(self.value, self.value.upper())


@dataclass
class SecurityFinding:
    tool: str
    severity: SecuritySeverity
    description: str
    file_or_endpoint: str
    evidence_snippet: str = ""
    cwe: str = ""
    owasp_category: str = ""
    remediation: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "severity": self.severity.value,
            "description": self.description,
            "file_or_endpoint": self.file_or_endpoint,
            "evidence_snippet": self.evidence_snippet,
            "cwe": self.cwe,
            "owasp_category": self.owasp_category,
            "remediation": self.remediation,
        }
