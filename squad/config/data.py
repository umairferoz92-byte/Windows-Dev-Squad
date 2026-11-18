"""The squad data location (%LOCALAPPDATA%\\squad) and first-run template copy."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "squad"


def ensure_template(name: str, template_source: str | Path) -> Path:
    """Copy a repo template into the data dir on first run; return the active path."""
    target = data_dir() / name
    if target.exists():
        return target
    src = Path(template_source)
    if not src.exists():
        return target
    data_dir().mkdir(parents=True, exist_ok=True)
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def active_config(name: str, template_source: str | Path) -> Path:
    return ensure_template(name, template_source)
