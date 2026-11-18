"""Typed tool definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: int
    description: str
