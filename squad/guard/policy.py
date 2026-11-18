"""Guard policy model and defaults.

The guard consumes a plain dict of policy (``guard.yaml`` is loaded by the CLI
layer, never by this module). ``Policy`` is a thin validated wrapper around
that dict; ``evaluate`` accepts either a ``Policy`` or a raw dict.
"""

from __future__ import annotations

import copy

DEFAULT_POLICY: dict = {
    "default_deny": True,
    "write_scope": [],
    "blocked_paths": [],
    "blocked_components": [".ssh", ".aws", ".azure", ".gnupg", ".git-credentials"],
    "sensitive_files": ["squad.yaml", "guard.yaml", "prices.yaml", ".env", ".env.example"],
    "sensitive_dirs": [".git", ".github"],
    "tools": {
        "read_file": {"tier": 0},
        "search_code": {"tier": 0},
        "repo_map": {"tier": 0},
        "git_diff": {"tier": 0},
        "git_status": {"tier": 0},
        "run_security_scan": {"tier": 0},
        "run_tests": {"tier": 0, "requires_isolation_level": 1},
        "run_lint": {"tier": 0, "requires_isolation_level": 1},
        "run_typecheck": {"tier": 0, "requires_isolation_level": 1},
        "edit_file": {"tier": 1},
        "git_commit": {"tier": 1},
        "install_dependencies": {"tier": 2},
        "git_push": {"tier": 3},
        "raw_shell": {"tier": 3},
        "credential_access": {"tier": 3},
        "invoke_squad": {"tier": 3},
        "admin_elevation": {"tier": 3},
    },
}


class Policy:
    def __init__(self, data: dict | None = None) -> None:
        # Merge over the defaults so a partial dict (e.g. only write_scope)
        # keeps the default tool tiers and blocked/sensitive lists.
        merged = copy.deepcopy(DEFAULT_POLICY)
        if data:
            for key, value in data.items():
                merged[key] = copy.deepcopy(value)
        self.data: dict = merged

    @classmethod
    def from_dict(cls, data: dict) -> Policy:
        return cls(data)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def __getitem__(self, key: str):
        return self.data[key]
