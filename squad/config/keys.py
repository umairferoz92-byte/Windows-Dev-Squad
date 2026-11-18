"""Load provider API keys from .env and the Windows Credential Manager.

Keys are loaded dynamically: any KEY=VALUE line in .env is imported into
os.environ, and any Generic credential named like ``*API_KEY*`` stored in the
Windows Credential Manager (``advapi32`` via ``ctypes``) is picked up too.
Known legacy keys (OPENROUTER_API_KEY, ANTHROPIC_API_KEY, etc.) are still
supported but any provider may supply its own key name (e.g. FREEllmAPI_KEY,
OPENAI_KEY). Loading never crashes if the Credential Manager is unavailable
(non-Windows, missing library): it simply returns silently.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from squad.config.data import data_dir

_CRED_TYPE_GENERIC = 1
_CRED_ENUMERATE_ALL_CREDENTIALS = 0


class CREDENTIAL(ctypes.Structure):
    """Minimal CREDENTIAL layout (fixed by the Windows SDK)."""

    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", wintypes.LPVOID),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserNm", wintypes.LPWSTR),
    ]


def _load_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Load any key into env — no whitelist restriction
        if key not in os.environ:
            os.environ[key] = value


def load_credential_manager_keys() -> None:
    """Read Generic credentials named like ``*API_KEY*`` into os.environ.

    Uses ``ctypes`` against ``advapi32`` (CredEnumerateW / CredReadW) so there
    are no third-party dependencies. If the Credential Manager cannot be reached
    (non-Windows, missing library, or an unexpected error) the call fails
    silently and returns without modifying ``os.environ``.
    """
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    except (AttributeError, OSError):
        return

    _configure_advapi32(advapi32)

    # Enumerate every credential and read those named like *API_KEY*.
    cred_pparray = ctypes.POINTER(ctypes.POINTER(CREDENTIAL))()
    count = wintypes.DWORD(0)
    ok = advapi32.CredEnumerateW(
        None,
        _CRED_ENUMERATE_ALL_CREDENTIALS,
        ctypes.pointer(count),
        ctypes.pointer(cred_pparray),
    )
    if not ok:
        return
    try:
        for i in range(count.value):
            cred = cred_pparray[i]
            if not cred or cred.contents.Type != _CRED_TYPE_GENERIC:
                continue
            target = cred.contents.TargetName or ""
            if "API_KEY" not in target.upper():
                continue
            _read_credential_secret(advapi32, target)
    finally:
        advapi32.CredFree(cred_pparray)


def _configure_advapi32(advapi32) -> None:
    """Set up ctypes prototypes on the loaded advapi32 handle.

    Only applies to real ``ctypes`` function objects (which expose ``restype``
    /``argtypes``). Test doubles built as plain Python classes skip this step
    gracefully — the enumeration/read calls still work because the fake returns
    the correct values directly.
    """
    if not all(
        hasattr(getattr(advapi32, name, None), "restype")
        for name in ("CredEnumerateW", "CredReadW", "CredFree")
    ):
        return
    advapi32.CredEnumerateW.restype = wintypes.BOOL
    advapi32.CredEnumerateW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(CREDENTIAL))),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
    ]
    advapi32.CredFree.restype = None
    advapi32.CredFree.argtypes = [wintypes.LPVOID]


def _read_credential_secret(advapi32, target: str) -> None:
    """Read one Generic credential's secret into os.environ by credential name."""
    pcred = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.pointer(pcred)):
        return
    try:
        cred = pcred.contents
        if cred.CredentialBlob and cred.CredentialBlobSize:
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            value = blob.decode("utf-16-le", errors="replace").rstrip("\x00")
            # Use the credential's own name as the env key (e.g. OPENROUTER_API_KEY).
            if target not in os.environ:
                os.environ[target] = value
    finally:
        advapi32.CredFree(pcred)


def load_keys() -> None:
    """Load keys from repo `.env`, the data-dir `.env`, then the Windows
    Credential Manager (first set wins). Any KEY=VALUE found is exported to
    os.environ; no hard-coded whitelist."""
    _load_file(Path(".env"))
    _load_file(data_dir() / ".env")
    load_credential_manager_keys()
