"""Squad version and packaging metadata."""

__version__ = "0.2.0"

PROJECT_NAME = "Windows Dev Squad"
PROJECT_URL = ""
LICENSE = "Proprietary"

CHANGELOG = """# Changelog

## 0.1.0 — Security Squad (Vibe Coding Blueprint)

### Added
- **Security Guard** (`squad security add-target`): signed `authorized_targets.yaml`,
  ownership statement required, `is_authorized()` gate, audit-logged.
- **Alfred** (`squad security check-tools`): 12-tool manifest, detection, per-tool
  install consent, checksum verification.
- **Nightwing** (`squad security nightwing`): Phase A passive recon (DNS, TLS,
  HTTP headers, robots.txt, exposed files, tech fingerprinting), Phase B static
  analysis (devhelper + Semgrep/Trivy/gitleaks when installed), Phase C active
  non-destructive (nmap, ZAP baseline, testssl.sh, gobuster) with fresh
  operator go-ahead per run.
- **Rate limiting + kill switch**: global request-rate limiter, `squad security stop`.
- **Oracle** (`squad security report`): executive summary, severity-sorted findings
  table with OWASP/CWE mapping, coverage note, raw-evidence appendix, secret
  redaction, Markdown/HTML/PDF output.

### Security
- All scans gated by the Security Guard; unauthorized targets are always refused.
- No destructive payloads by default; Phase C is non-destructive.
- Evidence redaction removes API keys/passwords before reporting.
"""


def version_string() -> str:
    return __version__
