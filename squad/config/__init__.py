"""Config validation, crash-recovery session, retention, keys, and data location."""

from __future__ import annotations

from squad.config.data import active_config, data_dir, ensure_template
from squad.config.keys import load_keys
from squad.config.retention import partition_by_age
from squad.config.session import Session, default_session_path
from squad.config.validate import KNOWN_PROVIDERS, validate_config

__all__ = [
    "validate_config",
    "KNOWN_PROVIDERS",
    "Session",
    "default_session_path",
    "partition_by_age",
    "load_keys",
    "KNOWN_KEYS",
    "data_dir",
    "ensure_template",
    "active_config",
]
