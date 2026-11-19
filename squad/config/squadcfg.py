"""squad configuration (squad.toml) — product feature.

Loads operator settings from a ``squad.toml`` file in the working directory or
``SQUAD_CONFIG``. Supports severity thresholds, tool toggles, rate limits,
notification channel, and scan defaults. Missing file -> sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def default_config_path() -> str:
    env = os.environ.get("SQUAD_CONFIG")
    if env:
        return env
    # Look for squad.toml in cwd, then home.
    cwd = Path.cwd() / "squad.toml"
    if cwd.exists():
        return str(cwd)
    home = Path.home() / "squad.toml"
    if home.exists():
        return str(home)
    return str(home)


@dataclass
class SquadConfig:
    # Scan defaults
    rate_limit_rps: float = 2.0  # global requests/sec cap
    fail_on: str = "high"  # gate threshold
    default_phases: str = "ab"  # phases run when none given
    ignore_statuses: tuple = ("accepted", "verified", "fixed")

    # Tool toggles (False disables a tool even if installed)
    use_nmap: bool = True
    use_semgrep: bool = True
    use_trivy: bool = True
    use_gitleaks: bool = True
    use_gobuster: bool = True
    use_ffuf: bool = True
    use_zap: bool = True
    use_testssl: bool = True

    # Notifications
    notify_channel: str = "console"  # console | desktop
    notify_on_complete: bool = True

    # Data
    data_dir: str = ""  # override for DB/authorized store

    _path: str = ""

    @property
    def path(self) -> str:
        return self._path


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def load_config(path: str | None = None) -> SquadConfig:
    """Load squad.toml, falling back to defaults when absent/unparseable."""
    cfg = SquadConfig()
    p = path or default_config_path()
    cfg._path = p
    if not os.path.exists(p):
        return cfg

    try:
        try:
            import tomllib  # py3.11+
        except ImportError:
            import tomli as tomllib
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return cfg  # ignore bad config, use defaults

    sec = data.get("scan", {})
    if "rate_limit_rps" in sec:
        cfg.rate_limit_rps = float(sec["rate_limit_rps"])
    if "fail_on" in sec:
        cfg.fail_on = str(sec["fail_on"])
    if "default_phases" in sec:
        cfg.default_phases = str(sec["default_phases"])

    tools = data.get("tools", {})
    for name in ("nmap", "semgrep", "trivy", "gitleaks", "gobuster", "ffuf", "zap", "testssl"):
        if name in tools:
            setattr(cfg, f"use_{name}", _as_bool(tools[name]))

    notif = data.get("notify", {})
    if "channel" in notif:
        cfg.notify_channel = str(notif["channel"])
    if "on_complete" in notif:
        cfg.notify_on_complete = _as_bool(notif["on_complete"])

    if "data_dir" in data:
        cfg.data_dir = str(data["data_dir"])

    return cfg
