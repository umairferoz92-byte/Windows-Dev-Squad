"""Offline tier of the chatbot: rule-based intent parsing + CLI command execution.

Turns natural-language requests into concrete ``squad`` subcommands and runs them
in-process (as subprocesses of the current interpreter). This tier never needs an
API key and works fully offline. Interactive-only commands (add-target, phase C,
check-tools --install) are surfaced as the exact command to run rather than hung.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Intent:
    kind: str  # 'action' | 'interactive' | 'help' | 'unknown' | 'llm' | 'quit'
    cmd: list[str] | None = None  # subcommand argv, e.g. ['security', 'nightwing', target]
    note: str = ""


# Keyword -> intent-builder callable. Pattern order matters (more specific first).
_PATTERNS: list[tuple[re.Pattern, Callable[[re.Match], Intent]]] = []


def _add(pattern: str, kind: str = "action"):
    def deco(fn):
        _PATTERNS.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn

    return deco


def _g(m, i: int, default: str = "") -> str:
    try:
        return (m.group(i) or default).strip()
    except (IndexError, TypeError):
        return default


# --- Offline action intents -----------------------------------------------
@_add(r"\b(review|audit\s+code|scan\s+code|check\s+code)\s+(.+)$")
def _review(m):
    return Intent("action", ["dev", "review", _g(m, 2)])


@_add(r"\b(generate\s+tests?|write\s+tests?|testgen|make\s+tests?)\s+(?:for\s+)?(.+)$")
def _testgen(m):
    return Intent("action", ["dev", "testgen", _g(m, 2)])


@_add(r"\b(refactor|modernize|improve\s+code)\s+(.+)$")
def _refactor(m):
    return Intent("action", ["dev", "refactor", _g(m, 2)])


@_add(r"\b(scan|pentest|test|nightwing)\s+([^\s]+)(?:\s+repo\s+(.+))?$")
def _scan(m):
    target = _g(m, 2)
    repo = _g(m, 3)
    cmd = ["security", "nightwing", target, "--phases", "ab"]
    if repo:
        cmd += ["--repo", repo]
    return Intent("action", cmd, note="Ran passive + static phases (Phase C needs interactive consent).")


@_add(r"\b(fetch\s+intel|update\s+intel|fetch\s+feed|refresh\s+intel|update\s+feed)\b")
def _fetch(m):
    return Intent("action", ["intel", "fetch"])


@_add(r"\b(search\s+intel|intel\s+search|search\s+(?:cve|cwe|threat|advisory))\s+(.+)$")
def _search(m):
    return Intent("action", ["intel", "search", _g(m, 2)])


@_add(r"\bsearch\s+(.+)$")
def _search_gen(m):
    return Intent("action", ["intel", "search", _g(m, 1)])


@_add(r"\b(security\s+status|scan\s+status)\b")
def _status(m):
    return Intent("action", ["security", "status"])


@_add(r"(?<!\bintel\s)\bstatus\b")
def _status_plain(m):
    return Intent("action", ["security", "status"])


@_add(r"\b(intel\s+status|feed\s+status)\b")
def _intel_status(m):
    return Intent("action", ["intel", "status"])


@_add(r"\b(doctor|self\s*[- ]?check|health\s*check|environment\s*check)\b")
def _doctor(m):
    return Intent("action", ["security", "doctor"])


@_add(r"\b(history|past\s+scans|list\s+scans)\b")
def _history(m):
    return Intent("action", ["security", "history"])


@_add(r"\b(check\s+tools|tools\s+status|what\s+tools)\b")
def _tools(m):
    return Intent("action", ["security", "check-tools"])


@_add(r"\b(export|dump)\s+(\S+)(?:\s+as\s+(\S+))?$")
def _export(m):
    return Intent("action", ["security", "export", _g(m, 2), "--format", _g(m, 3, "csv")])


# --- Interactive commands we must NOT auto-run ----------------------------
@_add(r"\b(add\s+target|authorize)\b")
def _add_target(m):
    return Intent("interactive", note="`squad security add-target` (interactive prompt — run it yourself).")


# --- LLM-routed intents (research / advanced) ----------------------------
_RESEARCH_HINT = re.compile(
    r"\b(research|explain|what\s+is|how\s+(?:do|does|can)|why\b|recommend|"
    r"best\s+practices|write\s+code|implement|build\s+an?|elaborate|"
    r"architect|compare|analyze\s+deep|threat\s+model)\b",
    re.IGNORECASE,
)


def classify_llm(text: str) -> bool:
    """True when this request should go to the LLM tier (research/advanced)."""
    return bool(_RESEARCH_HINT.search(text))


# --- Main parser ----------------------------------------------------------
def parse(text: str) -> Intent:
    """Parse a user message into an Intent."""
    t = text.strip()
    if not t:
        return Intent("unknown")
    low = t.lower()
    if low in ("exit", "quit", "bye", "q", "exit()"):
        return Intent("quit")
    if low in ("help", "?", "what can you do", "help me"):
        return Intent("help")

    # Bare action verbs need an argument — prompt for one instead of drifting
    # into LLM research and returning an unhelpful "no records matched" result.
    _bare_usage = {
        "review": "review <path>          e.g. `review practice/app.py`",
        "scan": "scan <target>          e.g. `scan 127.0.0.1`",
        "testgen": "testgen <file>        e.g. `testgen practice/app.py`",
        "generate tests": "testgen <file>",
        "write tests": "testgen <file>",
        "refactor": "refactor <file>      e.g. `refactor practice/app.py`",
        "code": "code <task>            describe a coding task in plain words",
        "research": "research <topic>     describe a topic to research",
        "search": "search <query>         e.g. `search sql injection`",
    }
    for verb, usage in _bare_usage.items():
        if low == verb:
            return Intent("interactive", cmd=None, note=f"Usage: {usage}")

    for pattern, fn in _PATTERNS:
        m = pattern.search(t)
        if m:
            return fn(m)

    # Everything else: try LLM if it looks researchy, else fall back to intel search.
    if classify_llm(t):
        return Intent("llm", cmd=None, note=t)
    return Intent("llm", cmd=None, note=t)  # default to LLM; offline fallback handles no-key


# --- Execution ------------------------------------------------------------
def _interp() -> str:
    """Return the interpreter to use for subprocesses.

    Prefer a sibling .venv interpreter next to the squad package so the chatbot
    keeps working with the project's real dependencies even if launched from a
    different python (e.g. an embedded/runtime python without typer installed).
    """
    import os
    from pathlib import Path

    squad_dir = Path(__file__).resolve().parent.parent  # .../squad/
    for venv in (squad_dir.parent / ".venv", Path(os.getcwd()) / ".venv"):
        for name in ("Scripts/python.exe", "bin/python", "bin/python3"):
            p = venv / name
            if p.exists():
                return str(p)
    return sys.executable


def run_command(cmd: list[str], timeout: int = 300) -> str:
    """Run a ``squad`` subcommand as a subprocess; return captured output.

    Uses the venv interpreter when available so dependency resolution matches
    the environment the chatbot itself is running in.
    """
    import os

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)  # strip any host/runtime pollution
    try:
        res = subprocess.run(
            [_interp(), "-m", "squad"] + cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"[chat] command timed out — killed after {timeout}s."
    out = res.stdout or ""
    if res.stderr:
        out += ("\n" + res.stderr) if out else res.stderr
    return out.strip() or f"(no output, rc={res.returncode})"
