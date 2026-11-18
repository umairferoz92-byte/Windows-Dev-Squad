"""Audit log: append-only, hash-chained."""

from __future__ import annotations

from squad.audit.audit import AuditLog, default_audit_path

__all__ = ["AuditLog", "default_audit_path"]
