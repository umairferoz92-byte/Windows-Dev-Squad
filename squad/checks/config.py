"""Load squad config files with ``yaml.safe_load`` only (rule 12)."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_yaml(path: str | Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def load_repo_config(path: str | Path = "squad.yaml") -> dict:
    return load_yaml(path)


def load_guard_policy(path: str = "guard.yaml") -> dict:
    return load_yaml(path)
