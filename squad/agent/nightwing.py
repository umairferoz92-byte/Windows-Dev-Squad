"""Nightwing: security testing agent (Prompt 3, 4).

Orchestrates:
- Phase A (Passive Recon): DNS records, TLS cert metadata, HTTP headers,
  robots.txt, exposed files, technology fingerprinting.
- Phase B (Static Analysis): devhelper SAST, plus Semgrep / Trivy / gitleaks
  when those tools are installed (offline — no traffic to the live target).
- Phase C (Active, non-destructive): nmap default scripts, ZAP baseline,
  testssl.sh, gobuster/ffuf content discovery — requires a fresh operator
  "go ahead" and rate limiting.

Gated by Security Guard's ``is_authorized(target)``.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import urllib.request
from dataclasses import dataclass, field

from squad.security_authorized import is_authorized
from squad.security_findings import SecurityFinding, SecuritySeverity


@dataclass
class ScanResult:
    target: str
    phase_a_findings: list[SecurityFinding] = field(default_factory=list)
    phase_b_findings: list[SecurityFinding] = field(default_factory=list)
    phase_c_findings: list[SecurityFinding] = field(default_factory=list)
    skipped_tools: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def total_findings(self) -> int:
        return len(self.phase_a_findings) + len(self.phase_b_findings) + len(self.phase_c_findings)


def _host_of(target: str) -> str:
    """Strip scheme/path to a bare hostname for DNS/TLS work."""
    t = target
    for scheme in ("http://", "https://"):
        if t.startswith(scheme):
            t = t[len(scheme) :]
            break
    return t.split("/")[0].split(":")[0]


class Nightwing:
    def __init__(self, target: str, local_repo_path: str | None = None):
        self.target = target
        self.local_repo_path = local_repo_path or os.getcwd()

    # -- authorization gate ------------------------------------------------
    def _require_authorized(self) -> None:
        if not is_authorized(self.target):
            raise PermissionError(f"Target '{self.target}' is not in the authorized-targets list.")

    def _require_repo_authorized(self) -> None:
        """Phase B reads local source, so the repo path must itself be
        authorized (F3): an operator cannot point --repo at an arbitrary
        directory and have SAST scan it regardless of authorization."""
        if not is_authorized(self.local_repo_path):
            raise PermissionError(
                f"Local repo path '{self.local_repo_path}' is not authorized. "
                f"Add it as an authorized target with `squad security add-target` "
                f"before running Phase B SAST on it."
            )

    def run_all(self, audit=None) -> ScanResult:
        """Run Phase A and Phase B sequentially, if authorized."""
        self._require_authorized()
        result = ScanResult(target=self.target)

        try:
            result.phase_a_findings.extend(self.run_phase_a(audit=audit))
        except Exception as e:
            result.errors.append(f"Phase A error: {e}")

        try:
            result.phase_b_findings.extend(self.run_phase_b(audit=audit))
        except Exception as e:
            result.errors.append(f"Phase B error: {e}")

        return result

    # -----------------------------------------------------------------------
    # Phase A: Passive Recon (Prompt 3, extended)
    # -----------------------------------------------------------------------
    def run_phase_a(self, audit=None) -> list[SecurityFinding]:
        """Passive recon: DNS, TLS cert, HTTP headers, exposed files, fingerprinting."""
        findings: list[SecurityFinding] = []
        if audit:
            audit.append("nightwing.phase_a.start", target=self.target)

        host = _host_of(self.target)

        # 1. DNS records
        try:
            ips = socket.getaddrinfo(host, None)
            resolved = sorted({ai[4][0] for ai in ips})
            if resolved:
                findings.append(
                    SecurityFinding(
                        tool="dns-recon",
                        severity=SecuritySeverity.INFO,
                        description=f"DNS resolved {host} -> {', '.join(resolved)}",
                        file_or_endpoint=self.target,
                        owasp_category="A01:2021-Broken Access Control",
                    )
                )
        except Exception as e:
            findings.append(
                SecurityFinding(
                    tool="dns-recon",
                    severity=SecuritySeverity.MEDIUM,
                    description=f"DNS resolution failed for {host}: {e}",
                    file_or_endpoint=self.target,
                    owasp_category="A01:2021-Broken Access Control",
                )
            )

        # 2. TLS certificate metadata (https target)
        url = self.target
        if not url.startswith(("http://", "https://")):
            url = "https://" + url if self._supports_tls(host) else "http://" + url
        if url.startswith("https://"):
            try:
                ctx = ssl.create_default_context()
                with socket.create_connection((host, 443), timeout=8) as sock:
                    with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                        cert = ssock.getpeercert()
                        if cert:
                            not_after = cert.get("notAfter", "unknown")
                            subject = dict(x[0] for x in cert.get("subject", []))
                            cn = subject.get("commonName", host)
                            findings.append(
                                SecurityFinding(
                                    tool="tls-cert",
                                    severity=SecuritySeverity.INFO,
                                    description=f"TLS cert CN={cn} expires {not_after}",
                                    file_or_endpoint=url,
                                    evidence_snippet=not_after,
                                    owasp_category="A02:2021-Cryptographic Failures",
                                )
                            )
            except Exception:
                pass  # plain-http server; skip silently

        # 3. HTTP headers
        self._check_headers(url, findings)

        # 4. Exposed files (.git, .env, robots.txt)
        self._check_exposed(url, findings)

        # 5. Technology fingerprinting
        self._fingerprint(url, findings)

        if audit:
            audit.append("nightwing.phase_a.complete", findings=len(findings))
        return findings

    def _supports_tls(self, host: str) -> bool:
        try:
            with socket.create_connection((host, 443), timeout=4):
                return True
        except Exception:
            return False

    def _check_headers(self, url: str, findings: list) -> None:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                hdrs = resp.headers
                missing = []
                for h in (
                    "Strict-Transport-Security",
                    "Content-Security-Policy",
                    "X-Frame-Options",
                    "X-Content-Type-Options",
                ):
                    if h.lower() not in {k.lower() for k in hdrs.keys()}:
                        missing.append(h)
                if missing:
                    findings.append(
                        SecurityFinding(
                            tool="header-check",
                            severity=SecuritySeverity.LOW,
                            description=f"Missing security headers: {', '.join(missing)}",
                            file_or_endpoint=url,
                            owasp_category="A05:2021-Security Misconfiguration",
                        )
                    )
        except Exception:
            pass

    def _check_exposed(self, url: str, findings: list) -> None:
        for path in ("/robots.txt", "/.git/", "/.env"):
            probe = url.rstrip("/") + path
            try:
                req = urllib.request.Request(probe, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        findings.append(
                            SecurityFinding(
                                tool="exposed-file-check",
                                severity=(SecuritySeverity.MEDIUM if ".git" in path or ".env" in path else SecuritySeverity.INFO),
                                description=f"Exposed file/directory discovered: {path}",
                                file_or_endpoint=probe,
                                owasp_category="A05:2021-Security Misconfiguration",
                            )
                        )
            except Exception:
                pass

    def _fingerprint(self, url: str, findings: list) -> None:
        """Lightweight tech fingerprinting from response headers/body."""
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                server = resp.headers.get("Server", "")
                via = resp.headers.get("Via", "")
                powered = resp.headers.get("X-Powered-By", "")
                sig = ", ".join(x for x in (server, powered, via) if x)
                if sig:
                    findings.append(
                        SecurityFinding(
                            tool="fingerprint",
                            severity=SecuritySeverity.INFO,
                            description=f"Technology fingerprint: {sig}",
                            file_or_endpoint=url,
                            evidence_snippet=sig,
                            owasp_category="A05:2021-Security Misconfiguration",
                        )
                    )
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Phase B: Static Analysis (Prompt 3, extended with real SAST tools)
    # -----------------------------------------------------------------------
    def run_phase_b(self, audit=None) -> list[SecurityFinding]:
        """Static analysis: devhelper SAST + Semgrep/Trivy/gitleaks. No network."""
        self._require_authorized()
        self._require_repo_authorized()
        findings: list[SecurityFinding] = []
        if audit:
            audit.append("nightwing.phase_b.start", repo=self.local_repo_path)

        # Core: squad devhelper scanner
        from squad.devhelper import scan_paths

        dev_results, _ = scan_paths([self.local_repo_path])
        for dr in dev_results:
            findings.append(
                SecurityFinding(
                    tool="squad-devhelper",
                    severity=(SecuritySeverity.HIGH if dr.severity.name in ("HIGH", "CRITICAL") else SecuritySeverity.MEDIUM),
                    description=dr.title,
                    file_or_endpoint=dr.file,
                    evidence_snippet=dr.evidence[:200],
                    owasp_category=(
                        "A03:2021-Injection" if "eval" in dr.title.lower() else "A07:2021-Identification and Authentication Failures"
                    ),
                )
            )

        # Optional real tools (only when installed; offline)
        repo = self.local_repo_path
        if shutil.which("semgrep"):
            try:
                proc = subprocess.run(
                    ["semgrep", "--json", "--quiet", "--metrics", "off", repo],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self._parse_semgrep(proc.stdout, findings)
            except Exception as e:
                findings.append(
                    SecurityFinding(
                        tool="semgrep",
                        severity=SecuritySeverity.INFO,
                        description=f"semgrep run failed: {e}",
                        file_or_endpoint=repo,
                        owasp_category="A06:2021-Vulnerable and Outdated Components",
                    )
                )
        else:
            findings.append(
                SecurityFinding(
                    tool="semgrep",
                    severity=SecuritySeverity.INFO,
                    description="Semgrep SAST skipped: semgrep not installed.",
                    file_or_endpoint=repo,
                    owasp_category="A05:2021-Security Misconfiguration",
                )
            )

        if shutil.which("gitleaks"):
            try:
                proc = subprocess.run(
                    [
                        "gitleaks",
                        "detect",
                        "--source",
                        repo,
                        "--no-git",
                        "--report-format",
                        "json",
                        "--report-path",
                        "-",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self._parse_gitleaks(proc.stdout, findings)
            except Exception as e:
                findings.append(
                    SecurityFinding(
                        tool="gitleaks",
                        severity=SecuritySeverity.INFO,
                        description=f"gitleaks run failed: {e}",
                        file_or_endpoint=repo,
                        owasp_category="A07:2021-Identification and Authentication Failures",
                    )
                )
        else:
            findings.append(
                SecurityFinding(
                    tool="gitleaks",
                    severity=SecuritySeverity.INFO,
                    description="Secret scanning skipped: gitleaks not installed.",
                    file_or_endpoint=repo,
                    owasp_category="A07:2021-Identification and Authentication Failures",
                )
            )

        if shutil.which("trivy"):
            try:
                proc = subprocess.run(
                    ["trivy", "fs", "--quiet", "--format", "json", "--skip-db-update", repo],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self._parse_trivy(proc.stdout, findings)
            except Exception as e:
                findings.append(
                    SecurityFinding(
                        tool="trivy",
                        severity=SecuritySeverity.INFO,
                        description=f"trivy run failed: {e}",
                        file_or_endpoint=repo,
                        owasp_category="A06:2021-Vulnerable and Outdated Components",
                    )
                )
        else:
            findings.append(
                SecurityFinding(
                    tool="trivy",
                    severity=SecuritySeverity.INFO,
                    description="Dependency CVE scan skipped: trivy not installed.",
                    file_or_endpoint=repo,
                    owasp_category="A06:2021-Vulnerable and Outdated Components",
                )
            )

        if audit:
            audit.append("nightwing.phase_b.complete", findings=len(findings))
        return findings

    def _parse_semgrep(self, out: str, findings: list) -> None:
        try:
            data = json.loads(out)
            for res in data.get("results", []):
                if not res.get("extra", {}).get("message"):
                    continue
                findings.append(
                    SecurityFinding(
                        tool="semgrep",
                        severity=SecuritySeverity.MEDIUM,
                        description=res["extra"]["message"].splitlines()[0][:200],
                        file_or_endpoint=res.get("path", ""),
                        evidence_snippet=(res.get("extra", {}).get("lines", "") or "")[:200],
                        cwe="CWE-79",
                        owasp_category="A03:2021-Injection",
                    )
                )
        except Exception:
            pass

    def _parse_gitleaks(self, out: str, findings: list) -> None:
        try:
            data = json.loads(out)
            findings_list = data if isinstance(data, list) else data.get("Findings", [])
            for f in findings_list:
                findings.append(
                    SecurityFinding(
                        tool="gitleaks",
                        severity=SecuritySeverity.HIGH,
                        description=f"Secret leak ({f.get('RuleID', 'unknown')})",
                        file_or_endpoint=f.get("File", ""),
                        evidence_snippet=(f.get("Secret", "") or "")[:100],
                        owasp_category="A07:2021-Identification and Authentication Failures",
                    )
                )
        except Exception:
            pass

    def _parse_trivy(self, out: str, findings: list) -> None:
        try:
            data = json.loads(out)
            for target in data.get("Results", []):
                for vuln in target.get("Vulnerabilities", []):
                    findings.append(
                        SecurityFinding(
                            tool="trivy",
                            severity=self._trivy_severity(vuln.get("Severity", "")),
                            description=f"{vuln.get('VulnerabilityID', 'CVE')}: {vuln.get('Title', '')[:140]}",
                            file_or_endpoint=vuln.get("PkgName", target.get("Target", "")),
                            evidence_snippet=vuln.get("InstalledVersion", ""),
                            owasp_category="A06:2021-Vulnerable and Outdated Components",
                        )
                    )
        except Exception:
            pass

    def _trivy_severity(self, s: str) -> SecuritySeverity:
        return {
            "CRITICAL": SecuritySeverity.CRITICAL,
            "HIGH": SecuritySeverity.HIGH,
            "MEDIUM": SecuritySeverity.MEDIUM,
            "LOW": SecuritySeverity.LOW,
        }.get(s.upper(), SecuritySeverity.INFO)

    # -----------------------------------------------------------------------
    # Phase C: Active, non-destructive scanning (Prompt 4, extended)
    # -----------------------------------------------------------------------
    def run_phase_c(self, confirm_commands=None, run_id=None, audit=None) -> list[SecurityFinding]:
        """Active but non-destructive scanning.

        Requires a fresh, explicit "go ahead" from the operator, shown with the
        exact commands and target. No exploit scripts.
        """
        from squad.agent.rate_limit import GLOBAL_KILL_SWITCH, GLOBAL_RATE_LIMITER

        self._require_authorized()
        findings: list[SecurityFinding] = []
        if not run_id:
            run_id = GLOBAL_KILL_SWITCH.new_run()

        commands = self._build_phase_c_commands()
        if confirm_commands is None or not confirm_commands(self.target, commands):
            raise PermissionError("Phase C requires a fresh 'go ahead' confirmation from the operator.")

        if audit:
            audit.append("nightwing.phase_c.start", target=self.target, run_id=run_id)

        # Nmap (default scripts only)
        if shutil.which("nmap"):
            cmd = ["nmap", "-sV", "-Pn", "--script", "default", self.target]
            out = self._run_child(run_id, cmd, GLOBAL_RATE_LIMITER, GLOBAL_KILL_SWITCH, 120)
            findings.append(
                SecurityFinding(
                    tool="nmap",
                    severity=SecuritySeverity.INFO,
                    description="Nmap default-script scan completed.",
                    file_or_endpoint=self.target,
                    evidence_snippet=(out or "")[:200],
                    owasp_category="A01:2021-Broken Access Control",
                )
            )

        # gobuster/ffuf content discovery (rate-limited, non-destructive)
        if shutil.which("gobuster") or shutil.which("ffuf"):
            if shutil.which("gobuster"):
                cmd = [
                    "gobuster",
                    "dir",
                    "-u",
                    self.target.rstrip("/") + "/",
                    "-w",
                    "/usr/share/wordlists/dirb/common.txt",
                    "-q",
                ]
            else:
                cmd = [
                    "ffuf",
                    "-u",
                    self.target.rstrip("/") + "/FUZZ",
                    "-w",
                    "/usr/share/wordlists/dirb/common.txt",
                ]
            out = self._run_child(run_id, cmd, GLOBAL_RATE_LIMITER, GLOBAL_KILL_SWITCH, 60)
            findings.append(
                SecurityFinding(
                    tool="content-discovery",
                    severity=SecuritySeverity.INFO,
                    description="Web content discovery completed.",
                    file_or_endpoint=self.target,
                    evidence_snippet=(out or "")[:200],
                    owasp_category="A01:2021-Broken Access Control",
                )
            )
        else:
            findings.append(
                SecurityFinding(
                    tool="content-discovery",
                    severity=SecuritySeverity.INFO,
                    description="Content discovery skipped: gobuster/ffuf not installed.",
                    file_or_endpoint=self.target,
                    owasp_category="A05:2021-Security Misconfiguration",
                )
            )

        # ZAP baseline
        zap = shutil.which("zap.sh") or shutil.which("zap")
        if zap:
            cmd = ["zap-baseline", "-t", self.target]
            out = self._run_child(run_id, cmd, GLOBAL_RATE_LIMITER, GLOBAL_KILL_SWITCH, 120)
            findings.append(
                SecurityFinding(
                    tool="zap",
                    severity=SecuritySeverity.INFO,
                    description="ZAP baseline scan completed.",
                    file_or_endpoint=self.target,
                    evidence_snippet=(out or "")[:200],
                    owasp_category="A03:2021-Injection",
                )
            )
        else:
            findings.append(
                SecurityFinding(
                    tool="zap",
                    severity=SecuritySeverity.INFO,
                    description="ZAP baseline skipped: OWASP ZAP not installed.",
                    file_or_endpoint=self.target,
                    owasp_category="A05:2021-Security Misconfiguration",
                )
            )

        # testssl.sh
        if shutil.which("testssl.sh"):
            cmd = ["testssl.sh", self.target]
            out = self._run_child(run_id, cmd, GLOBAL_RATE_LIMITER, GLOBAL_KILL_SWITCH, 120)
            findings.append(
                SecurityFinding(
                    tool="testssl",
                    severity=SecuritySeverity.INFO,
                    description="testssl.sh TLS configuration check completed.",
                    file_or_endpoint=self.target,
                    evidence_snippet=(out or "")[:200],
                    owasp_category="A02:2021-Cryptographic Failures",
                )
            )
        else:
            findings.append(
                SecurityFinding(
                    tool="testssl",
                    severity=SecuritySeverity.INFO,
                    description="TLS config not checked: testssl.sh not installed.",
                    file_or_endpoint=self.target,
                    owasp_category="A02:2021-Cryptographic Failures",
                )
            )

        if audit:
            audit.append("nightwing.phase_c.complete", run_id=run_id, findings=len(findings))
        return findings

    def _run_child(self, run_id, cmd, rate_limiter, kill_switch, timeout) -> str:
        rate_limiter.wait()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        kill_switch.register(run_id, proc)
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out = "(timed out)"
        return out

    def _build_phase_c_commands(self) -> list[str]:
        """Return the exact command list for Phase C, shown to the operator."""
        cmds = []
        if shutil.which("nmap"):
            cmds.append(f"nmap -sV -Pn --script default {self.target}")
        if shutil.which("gobuster"):
            cmds.append(f"gobuster dir -u {self.target.rstrip('/')}/ -w /usr/share/wordlists/dirb/common.txt -q")
        elif shutil.which("ffuf"):
            cmds.append(f"ffuf -u {self.target.rstrip('/')}/FUZZ -w /usr/share/wordlists/dirb/common.txt")
        if shutil.which("zap.sh") or shutil.which("zap"):
            cmds.append(f"zap-baseline -t {self.target}")
        if shutil.which("testssl.sh"):
            cmds.append(f"testssl.sh {self.target}")
        return cmds
