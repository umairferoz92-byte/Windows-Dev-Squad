"""Persistent conversation memory for ``squad chat``.

Turns are appended to a JSONL file under the squad data dir
(``%LOCALAPPDATA%\\squad\\chat\\history.jsonl`` on Windows). Each line is one
turn: ``{"role": "user"|"assistant"|"system", "content": "...", "ts": ...}``.
The most recent ``max_turns`` (whole turns, rounded up to pairs) are kept and
replayed into the LLM tier so the agent can actually *interact* with the user
across turns and across sessions instead of treating every message in
isolation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from squad.config.data import data_dir

MAX_TURNS = 40  # 20 user/assistant exchanges retained


def history_path() -> Path:
    return data_dir() / "chat" / "history.jsonl"


def _load() -> list[dict]:
    p = history_path()
    if not p.exists():
        return []
    turns: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("role") in ("user", "assistant", "system"):
                turns.append(obj)
    except OSError:
        return []
    return turns


def _trim(turns: list[dict]) -> list[dict]:
    if len(turns) <= MAX_TURNS:
        return turns
    # Keep the most recent MAX_TURNS, preserving an even (user/assistant) shape.
    keep = turns[-MAX_TURNS:]
    # Start from the first "user" turn in the retained window so the model sees
    # a clean prompt, not a dangling assistant reply.
    for i, t in enumerate(keep):
        if t.get("role") == "user":
            return keep[i:]
    return keep


def _save(turns: list[dict]) -> None:
    p = history_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for t in _trim(turns):
                fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    except OSError:
        # Memory is best-effort: a locked/roaming data dir must not break chat.
        return


def load_history() -> list[dict]:
    """Return the retained conversation as an OpenAI-style message list."""
    return _load()


def append(role: str, content: str) -> list[dict]:
    """Append one turn, persist, and return the trimmed history."""
    turns = _load()
    turns.append({"role": role, "content": content, "ts": time.time()})
    _save(turns)
    return _trim(turns)


def clear() -> None:
    """Wipe the persisted conversation (``squad chat --reset``)."""
    try:
        history_path().unlink(missing_ok=True)
    except OSError:
        pass
