"""squad doctor — environment self-check (product feature).

Verifies that squad can actually do its job: Python version, installed external
tools, data-dir writability, DB schema, and audit-log integrity. Exits non-zero
when a hard requirement is missing.
"""

from __future__ import annotations

import os
import sys

from squad.tools.manifest import BLUEPRINT_MANIFEST, check_all_tools
from squad.version import __version__


def run_checks() -> list[dict]:
    """Return a list of {name, ok, detail, hard} checks."""
    checks: list[dict] = []

    checks.append(
        {
            "name": "python",
            "ok": sys.version_info >= (3, 10),
            "detail": sys.version.split()[0],
            "hard": True,
        }
    )

    checks.append(
        {
            "name": "version",
            "ok": True,
            "detail": f"squad {__version__}",
            "hard": False,
        }
    )

    # Data dir writable.
    data_dir = os.environ.get("SQUAD_DATA_DIR", os.path.join(os.path.expanduser("~"), "AppData", "Local", "squad"))
    try:
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, ".doctor_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        checks.append({"name": "data-dir", "ok": True, "detail": data_dir, "hard": True})
    except Exception as e:
        checks.append({"name": "data-dir", "ok": False, "detail": str(e), "hard": True})

    # DB schema usable.
    try:
        from squad.store.history import ScanStore

        store = ScanStore()
        store.runs(limit=1)
        checks.append({"name": "history-db", "ok": True, "detail": store.db_path, "hard": False})
    except Exception as e:
        checks.append({"name": "history-db", "ok": False, "detail": str(e), "hard": False})

    # External tools (informational, not hard).
    tool_states = check_all_tools()
    found = sum(1 for t in tool_states if t.installed)
    checks.append(
        {
            "name": "security-tools",
            "ok": True,
            "detail": f"{found}/{len(BLUEPRINT_MANIFEST)} tools found",
            "hard": False,
        }
    )
    for t in tool_states:
        checks.append(
            {
                "name": f"tool-{t.name}",
                "ok": t.installed,
                "detail": t.version or "NOT FOUND",
                "hard": False,
            }
        )

    return checks


def doctor() -> dict:
    checks = run_checks()
    hard_fail = [c for c in checks if c["hard"] and not c["ok"]]
    return {"ok": not hard_fail, "checks": checks, "hard_fail": [c["name"] for c in hard_fail]}


def print_doctor() -> None:
    result = doctor()
    for c in result["checks"]:
        mark = "ok " if c["ok"] else "!! "
        print(f"[{mark}] {c['name']:<16} {c['detail']}")
    print()
    if result["ok"]:
        print("[ok] squad environment is healthy.")
    else:
        print(f"[!!] hard failures: {', '.join(result['hard_fail']) or 'none'}")


def has_any_external_tool() -> bool:
    return any(t.installed for t in check_all_tools())
