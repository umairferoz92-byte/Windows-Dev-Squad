"""Compliance mapping and report export (product feature).

Maps findings to OWASP Top 10 (already carried by Nightwing) plus NIST 800-53,
ISO 27001, and PCI DSS controls. Exports findings to CSV and JIRA-flavoured JSON
for ticketing / audit handoff.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Iterable, Sequence

from squad.security_findings import SecurityFinding

# OWASP 2021 -> control mappings.
_OWASP_CONTROLS = {
    "A01:2021-Broken Access Control": {
        "nist": "AC-3 Access Enforcement",
        "iso": "A.9.1.2 Access to Networks",
        "pci": "7.2 Restrict access to need-to-know",
    },
    "A02:2021-Cryptographic Failures": {
        "nist": "SC-13 Cryptographic Protection",
        "iso": "A.10.1.1 Policy on Cryptography",
        "pci": "2.3 Use strong cryptography",
    },
    "A03:2021-Injection": {
        "nist": "SI-10 Information Input Validation",
        "iso": "A.14.2.1 Secure Development Policy",
        "pci": "6.5.1 Handle injection flaws",
    },
    "A04:2021-Insecure Design": {
        "nist": "SA-15 Development, Test, Evaluation",
        "iso": "A.14.2.5 Secure System Engineering",
        "pci": "6.5.5 Handle insecure design",
    },
    "A05:2021-Security Misconfiguration": {
        "nist": "CM-6 Configuration Settings",
        "iso": "A.12.6.1 Management of Technical Vulnerabilities",
        "pci": "2.2 Change vendor defaults",
    },
    "A06:2021-Vulnerable and Outdated Components": {
        "nist": "RA-5 Vulnerability Scanning",
        "iso": "A.12.6.1 Management of Technical Vulnerabilities",
        "pci": "6.2 Ensure all system components patched",
    },
    "A07:2021-Identification and Authentication Failures": {
        "nist": "IA-2 Identification and Authentication",
        "iso": "A.9.4.2 Secure Log-on Procedures",
        "pci": "8.1.1 Assign unique IDs to each user",
    },
    "A08:2021-Software and Data Integrity Failures": {
        "nist": "SI-7 Software Integrity",
        "iso": "A.12.2.1 Controls Against Malicious Code",
        "pci": "6.4.2 Maintain change control",
    },
    "A09:2021-Security Logging and Monitoring Failures": {
        "nist": "AU-2 Audit Events",
        "iso": "A.12.4.1 Event Logging",
        "pci": "10.2 Audit trails",
    },
    "A10:2021-Server-Side Request Forgery": {
        "nist": "SC-7 Boundary Protection",
        "iso": "A.13.1.1 Network Controls",
        "pci": "6.5.8 Handle SSRF",
    },
}


def map_controls(owasp_category: str) -> dict:
    """Return {'nist','iso','pci'} controls for an OWASP category, or blanks."""
    entry = _OWASP_CONTROLS.get(owasp_category or "", {})
    return {
        "nist": entry.get("nist", ""),
        "iso": entry.get("iso", ""),
        "pci": entry.get("pci", ""),
    }


def to_csv(findings: Iterable[SecurityFinding]) -> str:
    """Render findings to CSV text."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["severity", "tool", "description", "file_or_endpoint",
                "cwe", "owasp", "nist", "iso", "pci", "remediation"])
    for f in findings:
        c = map_controls(f.owasp_category)
        w.writerow([f.severity.value, f.tool, f.description, f.file_or_endpoint,
                    f.cwe, f.owasp_category, c["nist"], c["iso"], c["pci"],
                    f.remediation])
    return buf.getvalue()


def to_jira_json(findings: Iterable[SecurityFinding]) -> str:
    """Render findings to a JIRA-flavoured JSON array."""
    rows = []
    for f in findings:
        c = map_controls(f.owasp_category)
        rows.append({
            "summary": f"[{f.severity.value.upper()}] {f.description}",
            "description": (f"Affected: {f.file_or_endpoint}\n\n"
                            f"OWASP: {f.owasp_category}\nCWE: {f.cwe}\n"
                            f"Remediation: {f.remediation}"),
            "labels": [f.tool, f.owasp_category, f.severity.value],
            "custom": c,
        })
    return json.dumps(rows, indent=2)


def summary_controls(findings: Iterable[SecurityFinding]) -> dict:
    """Aggregate distinct controls triggered across a set of findings."""
    nist, iso, pci = set(), set(), set()
    for f in findings:
        c = map_controls(f.owasp_category)
        if c["nist"]: nist.add(c["nist"])
        if c["iso"]: iso.add(c["iso"])
        if c["pci"]: pci.add(c["pci"])
    return {"nist": sorted(nist), "iso": sorted(iso), "pci": sorted(pci)}