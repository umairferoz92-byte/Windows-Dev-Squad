"""External security-tool manager: detect and install common offensive tools.

These tools (Nmap, Metasploit Framework, SQLMap, ...) are *external* — they are
not bundled with squad, and squad never runs them behind your back)Skip.

Guardrails (fail closed):
- Detection only: ``list``/``status`` just checks what is on PATH.
- Installation is operator-gated: ``squad tools install <name>`` *prints* the
  exact command; only ``squad tools install <name> --run`` actually executes it,
  and only through a package manager already on the system. squad never
  downloads or runs an installer on its own.
- Every action is written to the hash-chained audit log.
- Metasploit and other exploit-capable tools are for systems you own or are
  explicitly authorized to assess. No license is bundled here; you agree to the
  upstream project's license when you install it.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    display: str
    description: str
    binary: str
    # package identifiers per available manager; empty means not packaged there
    winget: str = ""
    scoop: str = ""
    choco: str = ""
    apt: str = ""
    brew: str = ""
    license: str = ""
    note: str = ""


# Well-known security tools squad can surface/install. Kept to common,
# licensed, widely-deployed assessment tools.
TOOL_REGISTRY: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="nmap",
        display="Nmap",
        binary="nmap",
        description="Network/port scanner with service and OS detection.",
        winget="Insecure.Nmap",
        scoop="nmap",
        choco="nmap",
        apt="nmap",
        brew="nmap",
        license="Nmap Public Source License",
        note="Passive/active network reconnaissance.",
    ),
    ToolSpec(
        name="metasploit",
        display="Metasploit Framework",
        binary="msfconsole",
        description="Exploitation and post-exploitation framework (authorized targets only).",
        winget="Rapid7.Metasploit",
        choco="metasploit",
        apt="metasploit-framework",
        brew="metasploit",
        license="Metasploit Framework License (BSD-3 with exceptions)",
        note="Exploit-capable. Use ONLY against systems you own or are explicitly authorized to assess.",
    ),
    ToolSpec(
        name="sqlmap",
        display="SQLMap",
        binary="sqlmap",
        description="Automatic SQL injection detection tool.",
        scoop="sqlmap",
        choco="sqlmap",
        apt="sqlmap",
        brew="sqlmap",
        license="GPL-2.0",
        note="Actively probes for SQLi; authorized targets only.",
    ),
    ToolSpec(
        name="nikto",
        display="Nikto",
        binary="nikto",
        description="Web server scanner for misconfigurations and known files.",
        choco="nikto",
        apt="nikto",
        brew="nikto",
        license="GPL-2.0",
        note="Web server scanner; run only against authorized targets.",
    ),
    ToolSpec(
        name="hydra",
        display="Hydra",
        binary="hydra",
        description="Network login brute-forcer (authorized targets only).",
        choco="hydra",
        apt="hydra",
        brew="hydra",
        license="AGPL-3.0",
        note="Brute-force tool. Use ONLY against authorized targets; rate-limit to avoid account lockout.",
    ),
    ToolSpec(
        name="gobuster",
        display="Gobuster",
        binary="gobuster",
        description="Directory/file/DNS brute-forcing over HTTP.",
        scoop="gobuster",
        choco="gobuster",
        apt="gobuster",
        brew="gobuster",
        license="Apache-2.0",
        note="Content discovery; authorized targets only.",
    ),
)


def _find(name: str) -> str | None:
    return shutil.which(name)


def get_tool(name: str) -> ToolSpec:
    key = name.strip().lower()
    for spec in TOOL_REGISTRY:
        if spec.name == key or spec.display.lower() == key:
            return spec
    raise KeyError(f"unknown tool '{name}' (known: {', '.join(s.name for s in TOOL_REGISTRY)})")


def detect(name: str) -> str | None:
    """Return the on-PATH path to a tool's binary, or None if not installed."""
    try:
        spec = get_tool(name)
    except KeyError:
        return None
    return _find(spec.binary)


def installed() -> dict[str, str | None]:
    return {spec.name: _find(spec.binary) for spec in TOOL_REGISTRY}


def _package_managers() -> list[tuple[str, str]]:
    """Return available managers as (manager, version) detected on PATH."""
    out: list[tuple[str, str]] = []
    for mgr in ("winget", "scoop", "choco", "apt", "brew"):
        path = _find(mgr)
        if path:
            out.append((mgr, path))
    return out


def build_install_command(name: str) -> str:
    """Build (without running) the exact install command for a tool.

    Raises RuntimeError if no package manager is available or the tool is not
    packaged under any available manager.
    """
    spec = get_tool(name)
    managers = _package_managers()
    for mgr, _path in managers:
        ident = getattr(spec, mgr)
        if ident:
            if mgr == "winget":
                return f'winget install -e --id "{ident}" --silent --accept-package-agreements --accept-source-agreements'
            if mgr == "scoop":
                return f"scoop install {ident}"
            if mgr == "choco":
                return f"choco install {ident} -y"
            if mgr == "apt":
                return f"sudo apt-get install -y {ident}"
            if mgr == "brew":
                return f"brew install {ident}"
    raise RuntimeError(f"'{spec.display}' is not packaged under an available manager ({', '.join(m for m, _ in managers) or 'none found'})")


def install_tool(name: str, run: bool = False, audit=None) -> tuple[str, int | None]:
    """Prepare (and optionally execute) an install for ``name``.

    Returns ``(command, exit_code)`` where ``exit_code`` is None when the
    command was only printed (``run=False``), or the subprocess return code
    when executed (``run=True``).
    """
    command = build_install_command(name)
    spec = get_tool(name)
    if audit is not None:
        audit.append("tools.install", tool=spec.name, run=run, command=command)
    if not run:
        return command, None
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)  # nosec B602  # tool installer commands require a shell; user-initiated, not attacker-controlled
    return command, proc.returncode


def status_rows() -> list[dict]:
    rows = []
    for spec in TOOL_REGISTRY:
        path = _find(spec.binary)
        rows.append(
            {
                "name": spec.name,
                "display": spec.display,
                "description": spec.description,
                "installed": path is not None,
                "path": path or "",
                "license": spec.license,
                "note": spec.note,
            }
        )
    return rows
