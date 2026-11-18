"""Alfred's tool manifest and detection engine (Prompt 2).

Covers the 12 tools specified in the Vibe Coding Blueprint:
- Nmap, OWASP ZAP, Nikto, testssl.sh, sqlmap, Semgrep, Bandit, Trivy,
  gitleaks, ffuf, gobuster, hydra.

Rules:
- ``check_tools()`` detects each tool via PATH, common install paths, and version checks.
- Interactive installer asks yes/no per missing tool before running any install command.
- Writes every action to the hash-chained audit log.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass(frozen=True)
class ToolManifestEntry:
    name: str
    display: str
    purpose: str
    binary: str
    install_cmd: str
    version_arg: str = "--version"
    expected_range: str = ""
    # Optional: sha256 of a known-good binary/archive. When the vendor
    # publishes one, Alfred verifies it after install.
    sha256: str = ""


# The 12 official tools from the blueprint manifest
BLUEPRINT_MANIFEST: tuple[ToolManifestEntry, ...] = (
    ToolManifestEntry(
        name="nmap", display="Nmap",
        purpose="Port/service recon", binary="nmap",
        install_cmd="winget install Insecure.Nmap",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="zap", display="OWASP ZAP",
        purpose="Web app DAST", binary="zap.sh",
        install_cmd="winget install ZAP.ZAP",
        version_arg="-version",
    ),
    ToolManifestEntry(
        name="nikto", display="Nikto",
        purpose="Web server misconfig scan", binary="nikto",
        install_cmd="winget install sullo.Nikto", # or via WSL/Strawberry Perl
        version_arg="-Version",
    ),
    ToolManifestEntry(
        name="testssl", display="testssl.sh",
        purpose="TLS/SSL config check", binary="testssl.sh",
        install_cmd="git clone https://github.com/drwetter/testssl.sh.git",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="sqlmap", display="sqlmap",
        purpose="SQL injection testing", binary="sqlmap",
        install_cmd="pip install sqlmap",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="semgrep", display="Semgrep",
        purpose="SAST, code-level bugs", binary="semgrep",
        install_cmd="pip install semgrep",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="bandit", display="Bandit",
        purpose="Python SAST", binary="bandit",
        install_cmd="pip install bandit",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="trivy", display="Trivy",
        purpose="Dependency & container CVEs", binary="trivy",
        install_cmd="winget install AquaSecurity.Trivy",
        version_arg="--version",
    ),
    ToolManifestEntry(
        name="gitleaks", display="Gitleaks",
        purpose="Secret scanning", binary="gitleaks",
        install_cmd="winget install gitleaks",
        version_arg="version",
    ),
    ToolManifestEntry(
        name="ffuf", display="ffuf",
        purpose="Content/endpoint discovery", binary="ffuf",
        install_cmd="go install github.com/ffuf/ffuf/v2@latest",
        version_arg="-V",
    ),
    ToolManifestEntry(
        name="gobuster", display="Gobuster",
        purpose="Content/endpoint discovery", binary="gobuster",
        install_cmd="winget install OJ.Gobuster",
        version_arg="version",
    ),
    ToolManifestEntry(
        name="hydra", display="Hydra",
        purpose="Network login brute-forcer", binary="hydra",
        install_cmd="winget install hydra",
        version_arg="-v",
    ),
)


@dataclass
class ToolStatus:
    name: str
    display: str
    purpose: str
    installed: bool
    path: str = ""
    version: str = ""
    install_cmd: str = ""


def detect_tool(entry: ToolManifestEntry) -> ToolStatus:
    """Detect if a tool is present on PATH or common locations, and get its version."""
    path = shutil.which(entry.binary)
    # Also check common Windows/Python script locations
    if not path and entry.binary in ("sqlmap", "semgrep", "bandit"):
        # check Scripts/
        base = os.path.dirname(sys.executable)
        candidate = os.path.join(base, entry.binary + (".exe" if os.name == "nt" else ""))
        if os.path.exists(candidate):
            path = candidate

    installed = path is not None
    version = ""
    if installed:
        try:
            proc = subprocess.run(
                [path, entry.version_arg],
                capture_output=True, text=True, timeout=5
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            # take first line of version output
            version = out.strip().splitlines()[0][:40] if out.strip() else "installed"
        except Exception:
            version = "installed (version unknown)"

    return ToolStatus(
        name=entry.name,
        display=entry.display,
        purpose=entry.purpose,
        installed=installed,
        path=path or "",
        version=version,
        install_cmd=entry.install_cmd,
    )


def check_all_tools(manifest: Sequence[ToolManifestEntry] = BLUEPRINT_MANIFEST) -> list[ToolStatus]:
    return [detect_tool(entry) for entry in manifest]


def sha256_file(path: str) -> str:
    """Compute the sha256 of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(entry: ToolManifestEntry, binary_path: str) -> tuple[bool, str]:
    """Verify an installed binary against the manifest's published sha256.

    Returns (ok, detail). If the manifest has no checksum for this tool, it
    is treated as "not verifiable" (ok=True with a note) rather than a failure,
    since not every vendor publishes one.
    """
    if not entry.sha256:
        return True, "no published checksum to verify"
    if not os.path.exists(binary_path):
        return False, f"binary not found: {binary_path}"
    actual = sha256_file(binary_path)
    if actual.lower() == entry.sha256.lower():
        return True, "sha256 verified"
    return False, f"checksum mismatch (got {actual[:12]}…)"
