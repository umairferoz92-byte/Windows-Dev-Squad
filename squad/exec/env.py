"""Scrubbed subprocess environment (rule 7).

Subprocesses must never inherit credentials. This filters on variable *names*
(conservative, not exhaustive) so obvious secrets are never passed to children.
"""

from __future__ import annotations

import os

SECRET_KEY_MARKERS: tuple[str, ...] = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "AUTH",
    "COOKIE",
)


def scrubbed_env() -> dict[str, str]:
    """Return a copy of os.environ without obvious secret-bearing variables."""
    clean: dict[str, str] = {}
    for name, value in os.environ.items():
        upper = name.upper()
        if any(marker in upper for marker in SECRET_KEY_MARKERS):
            continue
        clean[name] = value
    return clean
