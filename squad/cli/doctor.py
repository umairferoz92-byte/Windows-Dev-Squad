"""``squad doctor``: read-only environment and isolation diagnosis.

Collects machine facts (OS, Python, git, installed tools, proxy variables,
available isolation levels) and renders them. It never prints secrets: proxy
credentials are redacted and secret-bearing environment variables are never
enumerated.

Detection runs through a small ``Runner`` seam so tests can inject a fake
runner and stay offline and OS-independent.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from squad.cli.setup_help import setup_help_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROXY_VAR_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)

_SECRET_KEY_MARKERS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "AUTH",
)

DEFAULT_LOW_PRIV_USER = "squad-agent"
SANDBOX_EXE = r"C:\Windows\System32\WindowsSandbox.exe"
_VALID_USERNAME = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

TOOL_SPECS = {
    "pytest": ("pytest", "pytest"),
    "ruff": ("ruff", "ruff"),
    "bandit": ("bandit", "bandit"),
    "pip-audit": ("pip_audit", "pip-audit"),
}


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str], float], CommandResult]


def scrubbed_env() -> dict[str, str]:
    """Return os.environ minus obvious secret-bearing variables.

    Subprocesses started by doctor (and later the executor) must not inherit
    credentials. This filters on variable *names* and is deliberately
    conservative, not exhaustive.
    """
    clean: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(marker in upper for marker in _SECRET_KEY_MARKERS):
            continue
        clean[name] = value
    return clean


def default_runner(cmd: list[str], timeout: float = 15.0) -> CommandResult:
    """Run ``cmd`` as an argument list (never via a shell) with a scrubbed env."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=scrubbed_env(),
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(127, "", "command not found")
    except subprocess.TimeoutExpired:
        return CommandResult(124, "", "timed out")
    return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def redact_proxy_value(value: str) -> str:
    """Redact the userinfo (user:password) part of a proxy URL, if present."""
    if "://" in value:
        scheme, rest = value.split("://", 1)
        if "@" in rest:
            _userinfo, hostport = rest.rsplit("@", 1)
            return f"{scheme}://***@{hostport}"
    return value


def collect_os() -> dict:
    system = platform.system() or "Unknown"
    info: dict = {
        "system": system,
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "edition": None,
    }
    if system == "Windows":
        info["edition"] = platform.win32_edition() or None
    return info


def collect_python() -> dict:
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
    }


def collect_git(runner: Runner) -> dict:
    result = runner(["git", "--version"], 15.0)
    if result.returncode == 0:
        version = (result.stdout or result.stderr or "").strip()
        return {"installed": True, "version": version}
    return {"installed": False, "version": None}


def _script_available(script: str) -> bool:
    """True if the console script is on PATH or next to the running interpreter."""
    if shutil.which(script) is not None:
        return True
    # The running interpreter's directory is the venv Scripts/ (Windows) or
    # bin/ (POSIX); the console script lives there even when the venv is not
    # activated and its directory is not on PATH.
    bindir = os.path.dirname(sys.executable)
    name = script + ".exe" if os.name == "nt" else script
    return os.path.isfile(os.path.join(bindir, name))


def collect_tools() -> dict:
    tools: dict = {}
    for label, (module, script) in TOOL_SPECS.items():
        tools[label] = {
            "importable": importlib.util.find_spec(module) is not None,
            "on_path": _script_available(script),
        }
    return tools


def collect_proxy() -> dict:
    proxies: dict = {}
    for name in PROXY_VAR_NAMES:
        value = os.environ.get(name)
        if value:
            proxies[name] = {"set": True, "value": redact_proxy_value(value)}
        else:
            proxies[name] = {"set": False, "value": None}
    return proxies


# ---------------------------------------------------------------------------
# Pure decision helpers (unit-tested, OS-independent)
# ---------------------------------------------------------------------------


def sandbox_edition_supported(edition: str | None) -> bool:
    if not edition:
        return False
    lowered = edition.lower()
    return any(key in lowered for key in ("pro", "enterprise", "education"))


def level1_available(user_exists: bool, marker: dict | None) -> bool:
    return user_exists and bool(marker and marker.get("verified") is True)


# ---------------------------------------------------------------------------
# Marker + Windows-specific probes
# ---------------------------------------------------------------------------


def default_marker_path() -> str:
    if os.name == "nt":
        base = os.environ.get("ProgramData", r"C:\ProgramData")
        return os.path.join(base, "squad", "guard", "level1-firewall.json")
    return os.path.join("/var/lib", "squad", "guard", "level1-firewall.json")


def _read_marker(marker_path: str) -> dict | None:
    try:
        with open(marker_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _run_powershell(runner: Runner, script: str, timeout: float = 15.0) -> CommandResult:
    return runner(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout,
    )


def _detect_windows_level1(runner: Runner, low_priv_user: str, marker_path: str) -> dict:
    if not _VALID_USERNAME.match(low_priv_user):
        user_detail = "invalid user name (skipped)"
        user_exists = False
    else:
        # Get-LocalUser on a missing user throws a terminating error that exits
        # non-zero even with -ErrorAction SilentlyContinue, so use a try/catch
        # probe that always exits 0 and prints a deterministic FOUND/MISSING.
        script = (
            "try { Get-LocalUser -Name '" + low_priv_user + "' -ErrorAction Stop | Out-Null; Write-Output 'FOUND' } "
            "catch { Write-Output 'MISSING' }"
        )
        result = _run_powershell(runner, script)
        if result.returncode == 0 and result.stdout.strip() == "FOUND":
            user_exists = True
            user_detail = "present"
        elif result.returncode == 0 and result.stdout.strip() == "MISSING":
            user_exists = False
            user_detail = "not found"
        else:
            user_exists = False
            user_detail = "could not query (Get-LocalUser unavailable)"

    marker = _read_marker(marker_path)
    available = level1_available(user_exists, marker)
    firewall_detail = (
        "firewall block marker present and verified" if marker and marker.get("verified") is True else "firewall block NOT verified"
    )
    return {
        "name": "low-privilege user (Level 1)",
        "available": available,
        "detail": f"user {user_detail}; {firewall_detail}",
    }


def _hypervisor_present(runner: Runner) -> bool | None:
    result = _run_powershell(runner, "(Get-CimInstance Win32_ComputerSystem).HypervisorPresent")
    if result.returncode != 0:
        return None
    text = result.stdout.strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def _detect_windows_sandbox(runner: Runner, os_info: dict) -> dict:
    edition = os_info.get("edition")
    edition_ok = sandbox_edition_supported(edition)
    exe_ok = os.path.isfile(SANDBOX_EXE)
    hypervisor = _hypervisor_present(runner)
    available = edition_ok and exe_ok
    detail_parts = [
        "edition " + ("supported" if edition_ok else "unsupported (Windows Home lacks Sandbox)"),
        "WindowsSandbox.exe " + ("present" if exe_ok else "missing"),
        "hypervisor " + ("present" if hypervisor is True else "absent" if hypervisor is False else "unknown"),
    ]
    return {
        "name": "Windows Sandbox (Level 2)",
        "available": available,
        "detail": "; ".join(detail_parts),
    }


def _detect_wsl_docker(runner: Runner) -> dict:
    wsl: dict = {"installed": False}
    docker: dict = {"installed": False}

    if shutil.which("wsl"):
        result = runner(["wsl", "--status"], 15.0)
        combined = (result.stdout + result.stderr).lower()
        if result.returncode == 0 and "not installed" not in combined:
            wsl["installed"] = True
            version_result = runner(["wsl", "-l", "-v"], 15.0)
            if version_result.returncode == 0 and "version 2" in version_result.stdout.lower():
                wsl["wsl2"] = True
        else:
            wsl["detail"] = (result.stderr or result.stdout or "").strip()[:120] or "error"

    if shutil.which("docker"):
        result = runner(["docker", "--version"], 15.0)
        if result.returncode == 0:
            docker = {"installed": True, "version": (result.stdout or "").strip()}

    available = bool(wsl.get("wsl2")) or docker["installed"]
    detail_parts = []
    if docker["installed"]:
        detail_parts.append("docker " + docker.get("version", ""))
    if wsl.get("wsl2"):
        detail_parts.append("WSL2 available")
    if not detail_parts:
        detail_parts.append("neither WSL2 nor Docker detected")
    return {
        "name": "WSL2 / Docker (network none)",
        "available": available,
        "detail": "; ".join(detail_parts),
    }


def collect_isolation(
    runner: Runner,
    os_info: dict,
    low_priv_user: str = DEFAULT_LOW_PRIV_USER,
    marker_path: str | None = None,
) -> dict:
    system = os_info.get("system", "")
    marker_path = marker_path or default_marker_path()
    levels: dict = {
        "0": {
            "name": "own account (squad check only, trusted repos)",
            "available": True,
            "detail": "Always available; AI work must not run here.",
        }
    }

    if system == "Windows":
        levels["1"] = _detect_windows_level1(runner, low_priv_user, marker_path)
        levels["2"] = _detect_windows_sandbox(runner, os_info)
        levels["3"] = {
            "name": "dev VM",
            "available": None,
            "detail": "Cannot be auto-detected; configure manually if used.",
        }
        levels["4"] = _detect_wsl_docker(runner)
    else:
        levels["1"] = {
            "name": "low-privilege user (Level 1)",
            "available": False,
            "detail": "Not applicable on this OS (Windows-only Level 1).",
        }
        levels["2"] = {
            "name": "Windows Sandbox (Level 2)",
            "available": False,
            "detail": "Not applicable on this OS.",
        }
        levels["3"] = {
            "name": "dev VM / container",
            "available": None,
            "detail": "Cannot be auto-detected.",
        }
        levels["4"] = _detect_wsl_docker(runner)
    return levels


def _powershell_language_mode(runner: Runner) -> str | None:
    result = _run_powershell(runner, "$ExecutionContext.SessionState.LanguageMode")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def collect_doctor_facts(
    runner: Runner,
    low_priv_user: str = DEFAULT_LOW_PRIV_USER,
    marker_path: str | None = None,
) -> dict:
    os_info = collect_os()
    facts: dict = {
        "os": os_info,
        "python": collect_python(),
        "git": collect_git(runner),
        "tools": collect_tools(),
        "proxy": collect_proxy(),
        "isolation": collect_isolation(runner, os_info, low_priv_user, marker_path),
    }
    if os_info["system"] == "Windows":
        facts["powershell_language_mode"] = _powershell_language_mode(runner)
    else:
        facts["powershell_language_mode"] = None
    return facts


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _yes(value: bool) -> str:
    return "[green]yes[/green]" if value else "[red]no[/red]"


def render_report(facts: dict, console: Console) -> None:
    os_info = facts["os"]
    python = facts["python"]
    git = facts["git"]

    console.print(Panel.fit("[bold]squad doctor[/bold] — machine limits", border_style="cyan"))

    env_table = Table(title="Environment", show_header=False, box=box.SIMPLE)
    env_table.add_column("Item", style="bold")
    env_table.add_column("Value")
    os_label = escape(f"{os_info['system']} {os_info['release']}")
    if os_info.get("edition"):
        os_label += " " + escape(f"({os_info['edition']})")
    env_table.add_row("OS", os_label)
    env_table.add_row("Architecture", escape(os_info["machine"]))
    env_table.add_row("Python", f"{python['version']} ({python['implementation']})")
    env_table.add_row("Python executable", escape(python["executable"]))
    env_table.add_row("git", escape(git["version"]) if git["installed"] else "[red]not found[/red]")
    env_table.add_row("PowerShell language mode", escape(facts.get("powershell_language_mode") or "n/a"))
    console.print(env_table)

    tools_table = Table(title="Installed tools", show_header=True, box=box.SIMPLE)
    tools_table.add_column("Tool")
    tools_table.add_column("Importable")
    tools_table.add_column("On PATH")
    for label, tool in facts["tools"].items():
        tools_table.add_row(label, _yes(tool["importable"]), _yes(tool["on_path"]))
    console.print(tools_table)

    proxy_table = Table(title="Proxy variables (secrets redacted)", show_header=True, box=box.SIMPLE)
    proxy_table.add_column("Variable")
    proxy_table.add_column("Status")
    proxy_table.add_column("Value")
    for name, entry in facts["proxy"].items():
        proxy_table.add_row(name, "set" if entry["set"] else "unset", escape(entry["value"] or "-"))
    console.print(proxy_table)

    iso_table = Table(title="Isolation levels", show_header=True, box=box.SIMPLE)
    iso_table.add_column("Level")
    iso_table.add_column("Name")
    iso_table.add_column("Available")
    iso_table.add_column("Detail")
    for level in ("0", "1", "2", "3", "4"):
        item = facts["isolation"][level]
        available = item["available"]
        if available is True:
            status = "[green]yes[/green]"
        elif available is False:
            status = "[red]no[/red]"
        else:
            status = "[yellow]unknown[/yellow]"
        iso_table.add_row(level, item["name"], status, escape(item["detail"]))
    console.print(iso_table)

    console.print("[dim]squad doctor is read-only and never prints secrets.[/dim]")


def doctor_command(
    setup_help: bool = typer.Option(False, "--setup-help", help="Print one-time administrator setup steps and exit."),
    low_priv_user: str = typer.Option(
        DEFAULT_LOW_PRIV_USER,
        "--low-priv-user",
        help="Low-privilege account name to check for Level 1.",
    ),
) -> None:
    console = Console()
    if setup_help:
        console.print(setup_help_text(), markup=False)
        raise typer.Exit()
    facts = collect_doctor_facts(default_runner, low_priv_user=low_priv_user)
    render_report(facts, console)
