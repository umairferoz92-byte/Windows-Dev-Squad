"""Role -> allowed-model mapping from squad.yaml (models section)."""

from __future__ import annotations

ROLES = ("planner", "strong", "worker", "reviewer")


def role_allowed_models(models_config: dict, role: str) -> set[str]:
    return set(models_config.get(role) or [])


def all_allowed_models(models_config: dict) -> set[str]:
    out: set[str] = set()
    for role in ROLES:
        out |= set(models_config.get(role) or [])
    return out
