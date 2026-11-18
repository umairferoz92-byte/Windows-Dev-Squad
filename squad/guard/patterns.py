"""Destructive-command pattern detection (standard library only)."""

from __future__ import annotations

import re

# Patterns are case-insensitive and deliberately conservative (fail closed).
# They cover the shell/PowerShell/Unix destructive idioms that must never run
# even if a command-like argument slips past the tool tiers.
DEFAULT_DESTRUCTIVE_PATTERNS: tuple[str, ...] = (
    r"\brm\s+-[a-z]*r[a-z]*\s*(-[a-z]*f[a-z]*)?\s*[/\\]",  # rm -rf /
    r"\bdel\s+/[sqf]\b",  # del /s /q
    r"remove-item\b.*-(recurse|force)",  # Remove-Item -Recurse -Force
    r"format-volume\b",
    r"\bmkfs(\.[a-z0-9]+)?\b",
    r"\bdd\s+if=/dev/zero\b",
    r"git\s+push\s+.*(-f\b|--force)",
    r":\(\)\s*\{\s*:\|:&\s*\};:",  # fork bomb
    r"\bshutdown\b\s*/",
    r"\breg\s+delete\s+hklm",
    r"\bset-itemproperty\s+hk(?:lm|cu)",
)


def has_destructive(text: str, patterns: tuple[str, ...] | None = None) -> bool:
    """Return True if ``text`` matches any destructive pattern."""
    if not text:
        return False
    regexes = patterns or DEFAULT_DESTRUCTIVE_PATTERNS
    for pattern in regexes:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False
