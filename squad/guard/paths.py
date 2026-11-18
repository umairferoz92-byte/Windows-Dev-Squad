"""Path safety: canonicalization, write-scope containment, blocked paths.

Standard library only. Canonicalization is deliberately conservative (fail
closed): it decodes percent-encoded traversal, strips Windows aliasing, and
resolves symlinks/junctions/8.3 names before comparing, so an under-resolved
attacker path is treated as *more* suspicious rather than less.
"""

from __future__ import annotations

import os
import urllib.parse

from squad.guard.policy import DEFAULT_POLICY, Policy


class PathError(ValueError):
    """Raised when a path is malformed in a way that must fail closed."""


def _decode_percent(s: str, max_passes: int = 3) -> str:
    for _ in range(max_passes):
        decoded = urllib.parse.unquote(s)
        if decoded == s:
            break
        s = decoded
    return s


def _strip_win_device_prefix(s: str) -> str:
    # "\\?\C:\path" and "\\.\C:\path" bypass Win32 normalization; strip them so
    # that abspath/normpath below re-normalize and collapse any ".." they hid.
    if s.startswith("\\\\?\\"):
        s = s[4:]
        if s.lower().startswith("unc\\"):
            s = "\\\\" + s[3:]
        return s
    if s.startswith("\\\\.\\"):
        return s[4:]
    return s


def _strip_win_ads(s: str) -> str:
    # A drive-letter colon is legitimate; any later colon marks an alternate
    # data stream (file.txt:stream) that we drop for containment comparison.
    if ":" not in s:
        return s
    drive, sep, rest = s.partition(":")
    if sep and len(drive) == 1 and drive.isalpha():
        return drive + ":" + rest.split(":", 1)[0]
    return s.split(":", 1)[0]


def _strip_win_trailing(s: str) -> str:
    # Windows ignores trailing dots/spaces in path components. Strip them, but
    # leave components that are *only* dots/spaces (e.g. a literal "..." dir)
    # untouched.
    drive, tail = os.path.splitdrive(s)
    cleaned = []
    for part in tail.split("\\"):
        if part and part.strip(" .") == "":
            cleaned.append(part)
        else:
            cleaned.append(part.rstrip(" ."))
    return drive + "\\".join(cleaned)


def canonical(path: str) -> str:
    """Return the canonical absolute path for safe containment comparison."""
    s = _decode_percent(str(path))
    if "\x00" in s:
        raise PathError("path contains a null byte")
    s = os.path.expanduser(s)
    if os.name == "nt":
        s = _strip_win_device_prefix(s)
        s = _strip_win_ads(s)
    s = os.path.abspath(s)
    s = os.path.normpath(s)
    s = os.path.realpath(s)
    if os.name == "nt":
        s = os.path.normcase(s)
        s = _strip_win_trailing(s)
    return s


def fold_component(component: str) -> str:
    return component.lower() if os.name == "nt" else component


def path_components(path: str) -> list[str]:
    drive, tail = os.path.splitdrive(path)
    parts: list[str] = []
    if drive:
        parts.append(drive)
    for part in tail.split(os.sep):
        if part:
            parts.append(part)
    return parts


def is_within(path: str, roots) -> bool:
    """True if ``path`` canonicalizes to inside one of ``roots``."""
    target = canonical(path)
    for root in roots:
        r = canonical(root)
        if target == r:
            return True
        prefix = r if r.endswith(os.sep) else r + os.sep
        if target.startswith(prefix):
            return True
    return False


def _policy_data(policy) -> dict:
    if policy is None:
        return {}
    if isinstance(policy, Policy):
        return policy.data
    if isinstance(policy, dict):
        return policy
    return {}


def is_blocked(path: str, policy=None) -> bool:
    """True if ``path`` is under a blocked root or contains a blocked component."""
    data = DEFAULT_POLICY if policy is None else _policy_data(policy)
    target = canonical(path)
    for root in data.get("blocked_paths", []):
        if is_within(target, [root]):
            return True
    blocked = {fold_component(c) for c in data.get("blocked_components", [])}
    for component in path_components(target):
        if fold_component(component) in blocked:
            return True
    return False
