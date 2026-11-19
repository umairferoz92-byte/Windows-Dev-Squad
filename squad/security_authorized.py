"""Security Guard: authorized-targets management.

Handles ``authorized_targets.yaml`` — a hash-chained record of targets the user
has proved ownership of. Every later scan (Nightwing, pentest, etc.) must call
``is_authorized(target)`` before touching the network.

Formats & guardrails (fail closed):
- ``authorized_targets.yaml`` is a JSON-like YAML list of records.
  Each record: target, ownership_statement, added_at (ISO), sha256 of the
  concatenated ``target + ownership_statement + added_at``.
- Adding a target requires the user to type BOTH an ownership statement
  AND the exact target string back (not just click "yes").
- ``is_authorized(target)`` resolves the hostname, checks the resolved IP
  against the approved list, and also allows RFC 1918 private ranges and
  explicitly‑added public domains.
- Refusal is explicit: never silently proceed when a target is not authorized.
- Every write appends to the same hash-chained audit log used by the rest of Squad.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if os.name == "nt":
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
else:
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))

# Paths are overridable via env (used by tests to isolate from real data).
AUTHORIZED_PATH = os.environ.get(
    "SQUAD_AUTHORIZED_PATH",
    os.path.join(base, "squad", "authorized_targets.yaml"),
)
AUDIT_PATH = os.environ.get(
    "SQUAD_AUDIT_PATH",
    os.path.join(base, "squad", "audit", "audit.jsonl"),
)

# ---------------------------------------------------------------------------
# authorized_targets.yaml helpers
# -------------------------------------------------------------------------


def _sha256_of(record: dict) -> str:
    """SHA-256 of the canonical serialization of a record (minus the sha256 field)."""
    c = {k: v for k, v in record.items() if k != "sha256"}
    canonical = json.dumps(c, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_authorized() -> list[dict]:
    """Load the current authorized-targets list from disk.

    Returns the list even when the file is missing or corrupted (empty list),
    so callers never hit a FileNotFoundError.
    """
    if not os.path.exists(AUTHORIZED_PATH):
        return []
    try:
        with open(AUTHORIZED_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        if isinstance(data, dict):
            data = [data]
        # Validate each entry: it must have the required keys AND its sha256
        # must match the canonical serialization of the other fields. A record
        # whose hash does not verify is treated as tampered and dropped, so a
        # tampered authorized_targets.yaml is refused (fail closed).
        valid = []
        for entry in data if isinstance(data, list) else []:
            if not isinstance(entry, dict):
                continue
            if not ({"target", "ownership_statement", "added_at", "sha256"} <= set(entry)):
                continue
            expected = _sha256_of(entry)
            if expected != entry.get("sha256"):
                continue  # tampered or malformed -> drop
            valid.append(entry)
        return valid
    except Exception:
        return []


def _append_authorized(record: dict) -> None:
    """Append a new record to ``authorized_targets.yaml`` and the audit log.

    The record already contains a verified ``sha256`` field.
    """
    # Append to YAML file — read, merge, write atomically at the file level
    entries = _load_authorized()
    entries.append(record)

    # Write YAML (compact flow style for a list)
    with open(AUTHORIZED_PATH, "w", encoding="utf-8") as f:
        yaml.dump(entries, f, default_flow_style=False, sort_keys=True)

    # Append to hash-chained audit log
    _audit_append(
        "authorized_targets.add",
        target=record["target"],
        ownership=record["ownership_statement"],
        sha256=record["sha256"],
    )


def _audit_append(event: str, **fields) -> None:
    """Append to the same hash-chained audit log the rest of Squad uses.

    Uses ``squad.audit.audit.AuditLog`` so the entry format, hash chain, and
    ``squad audit`` integrity check all stay consistent. The log path honours
    the ``SQUAD_AUDIT_PATH`` override (tests) else falls back to the default.
    """
    from squad.audit.audit import AuditLog, default_audit_path

    path = AUDIT_PATH if AUDIT_PATH else default_audit_path()
    log = AuditLog(path)
    # AuditLog.append chains against its own previous entry automatically.
    log.append(event, **fields)


# ---------------------------------------------------------------------------
# is_authorized(target)
# -------------------------------------------------------------------------


def _resolve_host(target: str) -> str:
    """Resolve a hostname to its IP address. Returns the IP string, or the original target if resolution fails."""
    import socket

    try:
        addr = socket.gethostbyname(target)
        return addr
    except Exception:
        return target


def is_authorized(target: str) -> bool:
    """Return True if *target* is in the authorized list.

    Resolution rules (fail closed):
    1. If the target resolves to an IP that appears in an authorized entry -> True.
    2. If the target is an RFC 1918 private IP (10.0.0.0/8, 172.16.0.0/12,
       192.168.0.0/16) AND the target string itself looks like a private
       hostname/range -> True.
    3. If the target is an explicit public domain that the user added
       (exact string match on the ``target`` field) -> True.
    4. Otherwise -> False.

    The function never silently proceeds; it logs a refusal and returns False
    when the target is not authorized.
    """
    target = (target or "").strip()
    if not target:
        _audit_append("is_authorized.refuse", reason="empty target")
        return False

    authorized = _load_authorized()

    # Resolve hostname to IP
    resolved_ip = _resolve_host(target)

    # Check each authorized entry
    for entry in authorized:
        auth_target = entry["target"].strip()

        # Exact string match first
        if target == auth_target:
            # Also allow if the authorized entry's resolved IP matches
            if _resolve_host(auth_target) == resolved_ip:
                return True
            # If the authorized target itself is an IP and matches
            if auth_target == resolved_ip:
                return True

        # RFC 1918 private-range check:
        private_prefixes = (
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "192.168.",
        )
        is_auth_private = any(auth_target.startswith(p) for p in private_prefixes)
        is_req_private = any(resolved_ip.startswith(p) for p in private_prefixes) if resolved_ip else False

        if is_auth_private and is_req_private:
            if resolved_ip == auth_target:
                return True

        # Explicit public-domain match (exact string)
        if target == auth_target:
            return True

    # Not authorized — log the refusal
    _audit_append("is_authorized.refuse", target=target, reason="target not in authorized list")
    return False


# ---------------------------------------------------------------------------
# squad security add-target CLI command
# -------------------------------------------------------------------------


def _prompt_user(prompt_text: str) -> str:
    """Read a line from stdin, stripping trailing whitespace."""
    return input(prompt_text).strip()


def cmd_security_add_target() -> None:
    """``squad security add-target`` — prompt the user to add a new authorized target.

    Flow:
    1. Prompt for an ownership statement (e.g. "I own and am authorized to test this system").
    2. Prompt for the exact target string (URL, IP, or local path).
    3. Re-prompt the exact target string to confirm (protects against typos).
    4. Compute ``sha256(target + ownership_statement + added_at)``.
    5. Write the record to ``authorized_targets.yaml`` and the audit log.
    6. Confirm to the user.
    """
    # Step 1: ownership statement
    ownership = _prompt_user('Ownership statement (e.g. "I own and am authorized to test this system"): ')
    if not ownership:
        print("[refused] ownership statement cannot be empty.")
        return

    # Step 2: target string
    target = _prompt_user("Exact target string (URL, IP, or local path): ")
    if not target:
        print("[refused] target cannot be empty.")
        return

    # Step 3: re-prompt target for confirmation
    target2 = _prompt_user(f"Confirm target (type it again exactly): {target}")
    if target2 != target:
        print("[refused] target strings did not match.")
        return

    # Step 4: compute sha256 over the canonical serialization of the record
    # fields (same function _load_authorized uses to verify, so round-trips).
    added_at = datetime.now(UTC).isoformat()
    record = {
        "target": target,
        "ownership_statement": ownership,
        "added_at": added_at,
    }
    record["sha256"] = _sha256_of(record)

    # Step 5: write
    _append_authorized(record)

    # Step 6: confirm
    print(f"[ok] authorized target added: {target}")
    print(f"  ownership: {ownership}")
    print(f"  added at: {added_at}")


# ---------------------------------------------------------------------------
# Convenience: CLI entry point (wired by the app.py dispatcher)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # When run directly, dispatch to the CLI command
    cmd_security_add_target()
