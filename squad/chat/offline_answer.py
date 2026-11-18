"""Offline knowledge base: keyword-matched security/coding answers.

Lets the chatbot answer common questions with **zero** dependencies — no
TensorFlow, no LLM key, no network. This is the guaranteed "better offline
response" tier that works on any user's machine regardless of what ML or
LLM tooling they have (or don't have).

Entries are matched by keyword against the user's question; the best (most
keyword hits) match wins. Each answer is concise, security-first, and points
to concrete ``squad`` commands where relevant.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A small, dense KB. ``keywords`` are lowercase substrings matched against the
# lowercased question. ``answer`` is returned verbatim.
@dataclass
class _Entry:
    keywords: tuple[str, ...]
    answer: str


_KB: list[_Entry] = [
    _Entry(
        ("sql injection", "sqli", "sql"),
        "SQL injection: never concatenate user input into SQL. Use parameterized "
        "queries / prepared statements (e.g. `cur.execute('... WHERE id = ?', (id,))`). "
        "Validate and bind all inputs, and use least-privilege DB accounts. "
        "Try: `squad dev review <file>` to scan code for this pattern, "
        "`squad security nightwing <target>` for a live scan of an authorized target.",
    ),
    _Entry(
        ("xss", "cross-site", "script injection"),
        "Cross-Site Scripting (XSS): never insert raw user input into HTML/JS. "
        "Encode/escape on output (`html.escape`), use a CSP, and prefer frameworks "
        "that auto-escape. Validate on input. If reviewing code: `squad dev review <file>`.",
    ),
    _Entry(
        ("csrf", "request forgery", "cross-site request"),
        "CSRF: protect state-changing requests with per-session tokens and "
        "SameSite cookies. Verify the Origin/Referer on sensitive actions. "
        "Never rely on GET for state changes.",
    ),
    _Entry(
        ("ssrf", "server-side request"),
        "SSRF: never let user-supplied URLs/redirects reach internal services. "
        "Validate and allowlist destinations, block metadata endpoints "
        "(169.254.169.254, localhost), and disable redirects on fetch clients.",
    ),
    _Entry(
        ("rce", "remote code", "code execution", "command injection", "shell injection"),
        "RCE / command injection: avoid `shell=True`, `os.system`, `eval`/`exec` on "
        "untrusted input. Prefer argument-list subprocess calls and strict allowlists. "
        "This is a critical (OWASP A03) finding — review with `squad dev review <file>`.",
    ),
    _Entry(
        ("auth", "authentication", "password", "hash", "bcrypt", "argon", "session"),
        "Authentication & hashing: use a slow, salted hash (Argon2id or bcrypt) — "
        "never MD5/SHA1 for passwords. Enforce MFA, strong password policy, and "
        "short-lived signed sessions with secure flags (HttpOnly, Secure, SameSite).",
    ),
    _Entry(
        ("tls", "ssl", "https", "encryption", "certificate", "handshake"),
        "TLS/HTTPS: terminate TLS at the edge, enforce TLS 1.2+, HSTS, and secure "
        "cipher suites. Never downgrade to plaintext. Test with `squad security "
        "nightwing <target>` (Phase A checks headers/TLS) or `testssl.sh`.",
    ),
    _Entry(
        ("owasp", "top 10", "top ten"),
        "OWASP Top 10 (key items): A01 broken access control, A02 crypto failures, "
        "A03 injection, A04 insecure design, A05 security misconfiguration, A06 "
        "vulnerable components, A07 identification/auth failures, A08 software/data "
        "integrity, A09 logging/monitoring, A10 SSRF. Map findings to these with "
        "`squad security report <target>`.",
    ),
    _Entry(
        ("port", "nmap", "scan", "recon", "footprint", "enumerate", "nightwing"),
        "Recon/scans: use `squad security nightwing <target>` — Phase A (passive "
        "recon + TLS/fingerprint) and Phase B (static analysis) run automatically; "
        "Phase C (nmap/ZAP) needs your interactive consent. Add authorized targets "
        "first with `squad security add-target`.",
    ),
    _Entry(
        ("reverse shell", "shell"),
        "Reverse shells: these are a live-attack technique. Only use on systems you "
        "own or are authorized to test. For blue-team understanding, they exploit "
        "RCE to spawn a callback; defense = patch the RCE, egress firewall rules, "
        "and host-based detection (EDR).",
    ),
    _Entry(
        ("buffer", "overflow", "memory"),
        "Buffer/memory safety: in C/C++ prefer bounds-checked APIs, ASAN, and "
        "modern smart pointers; avoid `strcpy`/`gets`. In managed languages the "
        "runtime checks bounds — focus on logic flaws and deserialization instead.",
    ),
    _Entry(
        ("deserialization", "pickle", "yaml.load", "unpickle"),
        "Insecure deserialization: never `pickle.loads`/`yaml.load` untrusted data. "
        "Use safe formats (JSON) or verify signatures. This is a high-risk OWASP "
        "finding — flag it in `squad dev review`.",
    ),
    _Entry(
        ("cve", "advisory", "vulnerability", "exploit", "zero-day"),
        "Vulnerabilities/CVEs: search live advisories with `squad intel search <cve>` "
        "(e.g. `search cve-2021-44228`). Keep dependencies current and track CVSS "
        "severity; test your exposure with `squad security nightwing <target>`.",
    ),
    _Entry(
        ("api", "rest", "endpoint", "hardening", "secure api"),
        "API hardening: authenticate every request, rate-limit, validate/schema-encode "
        "inputs, never leak stack traces, use least-privilege tokens, and log "
        "auditable events. Review endpoints with `squad security nightwing <target>`.",
    ),
    _Entry(
        ("log", "monitor", "logging", "detection", "edr", "siem"),
        "Logging & monitoring (OWASP A09): log auth failures, access, and "
        "state-changing events with timestamps and structured context; alert on "
        "anomalies. Good logs are your detection and forensics backbone.",
    ),
    _Entry(
        ("docker", "container", "kubernetes", "k8s", "supply chain"),
        "Container/supply-chain security: pin image digests, scan for CVEs, drop "
        "root, read-only filesystems, sign artifacts, and scan dependencies in CI. "
        "Check your tooling with `squad security check-tools`.",
    ),
    _Entry(
        ("github", "git", "repo", "secret", "token leak", "credentials"),
        "Secret management: never commit API keys/tokens — use env vars or a vault "
        "(e.g. Windows Credential Manager / a secrets manager), rotate leaked "
        "secrets immediately, and add secret-scanning (gitleaks) to CI.",
    ),
    _Entry(
        ("refactor", "clean code", "maintain", "legacy", "simplify"),
        "Refactoring: prefer small functions with clear names, remove duplication, "
        "add type hints and error handling, keep dependencies currentable. Run "
        "`squad dev refactor <file>` for a modernized suggestion.",
    ),
    _Entry(
        ("test", "unit test", "pytest", "tdd", "coverage"),
        "Testing: write focused unit tests for the interesting logic, prefer TDD for "
        "new behavior, and keep the suite fast. Generate a starting suite with "
        "`squad dev testgen <file>`.",
    ),
    _Entry(
        ("python", "django", "flask", "code"),
        "Python: follow PEP 8/type hints, use virtual environments, keep deps pinned, "
        "and prefer the standard library + well-maintained packages. Scan your code "
        "with `squad dev review <file>`.",
    ),
    _Entry(
        ("threat model", "threat modeling", "stride", "attack surface"),
        "Threat modeling: enumerate assets, trust boundaries, and STRIDE-based "
        "threats; rank by likelihood/impact and choose mitigations. Good inputs: "
        "architecture, data flows, and past findings from `squad security history`.",
    ),
    _Entry(
        ("zero trust", "trust boundary", "network"),
        "Zero trust: assume breach — authenticate and authorize every request, "
        "micro-segment the network, encrypt everywhere, and verify continuously. "
        "Defense-in-depth over perimeter trust.",
    ),
    _Entry(
        ("phishing", "social engineering", "malware", "ransomware"),
        "Threats (phishing/malware/ransomware): user awareness + email filtering, "
        "restrict script execution, application allowlisting, frequent patching, "
        "and offline verified backups are the top controls. Phishing = the #1 "
        "initial-access vector.",
    ),
    _Entry(
        ("whois", "dns", "subdomain", "footprint", "exposure"),
        "Exposure/recon: DNS, subdomains, and open ports expand your attack surface. "
        "Use `squad security nightwing <target>` Phase A for passive recon and "
        "tighten firewall/allowlists for anything not intentionally public.",
    ),
    _Entry(
        ("help", "how do i", "how to", "what can", "commands", "usage"),
        "I can review code (`review <file>`), generate tests (`testgen <file>`), "
        "refactor (`refactor <file>`), run scans (`scan <target>`), search "
        "advisories (`search <cve>`), check tools (`check tools`), run a doctor "
        "check, export findings, and more. Type `help` for the full list.",
    ),
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s/.-]", " ", text.lower())


def lookup(question: str) -> str | None:
    """Return the best-matching offline answer, or None if nothing matches."""
    q = _normalize(question)
    best: tuple[int, _Entry] | None = None
    for e in _KB:
        hits = sum(1 for kw in e.keywords if kw in q)
        if hits and (best is None or hits > best[0]):
            best = (hits, e)
    if best is None:
        return None
    # Require at least a token overlap; a single generic keyword ("code", "help")
    # should not hijack every unrelated question.
    hits = best[0]
    if hits == 1 and best[1].keywords[0] in ("code", "help", "sql", "port"):
        # Keep 1-hit answers only when the question is short (likely on-topic).
        if len(q.split()) > 8:
            return None
    return best[1].answer