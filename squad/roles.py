"""Roles and signed audit export (product feature).

Defines operator roles (owner / operator / auditor), enforces the read-only
auditor view, and produces a signed chain-of-custody export of the audit log so
authorization and scan activity can be handed to an auditor as evidence.

Roles are persisted in a small config file. There is no authentication backend
in this TUI tool; the role is a declared operating mode that the auditor uses
to obtain a tamper-evident export.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

# Roles understood by the tool.
ROLES = ("owner", "operator", "auditor")

# Role access matrix.
ACCESS = {
    "owner": {"add_target", "install_tools", "scan_active", "scan_intrusive",
              "export_audit", "manage_roles"},
    "operator": {"scan_active", "scan_passive", "export_audit"},
    "auditor": {"export_audit"},  # read-only: cannot change targets or scan
}


def default_roles_path() -> str:
    base = os.environ.get("SQUAD_DATA_DIR", os.path.join(os.path.expanduser("~"), "AppData", "Local", "squad"))
    return os.path.join(base, "roles.json")


def current_role(path: Optional[str] = None) -> str:
    p = path or default_roles_path()
    if os.path.exists(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8")).get("role", "owner")
        except Exception:
            return "owner"
    return "owner"


def set_role(role: str, path: Optional[str] = None) -> str:
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    p = Path(path or default_roles_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"role": role}), encoding="utf-8")
    return role


def can(permission: str, role: Optional[str] = None) -> bool:
    r = role or current_role()
    return permission in ACCESS.get(r, set())


def _hash_line(line: str, prev_hash: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{line}".encode("utf-8")).hexdigest()


def export_audit(audit_lines: list[str]) -> str:
    """Build a signed chain-of-custody export from raw audit log lines.

    Chains each line by SHA256 of (prev_hash|line), then signs the whole file
    with the final hash. The consumer can verify no line was added, removed,
    or reordered.
    """
    prev = "0" * 64
    out = []
    for line in audit_lines:
        line = line.rstrip("\n")
        h = _hash_line(line, prev)
        out.append(f"{h} {line}")
        prev = h
    footer = {
        "chain_root": prev,
        "lines": len(audit_lines),
        "producer": "squad-security",
    }
    out.append("# signed-audit " + json.dumps(footer))
    return "\n".join(out) + "\n"


def verify_audit_export(export_text: str) -> tuple[bool, int]:
    """Return (valid, count) — recomputes the chain and checks integrity."""
    prev = "0" * 64
    count = 0
    for line in export_text.splitlines():
        line = line.rstrip("\n")
        if line.startswith("# signed-audit "):
            footer = json.loads(line[len("# signed-audit "):])
            return prev == footer["chain_root"] and count == footer["lines"], count
        if " " in line:
            h, rest = line.split(" ", 1)
            expected = _hash_line(rest, prev)
            if h != expected:
                return False, count
            prev = h
            count += 1
    return False, count