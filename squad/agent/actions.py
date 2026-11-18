"""Parse the JSON action the model returns."""

from __future__ import annotations

import json


class ActionError(RuntimeError):
    pass


def parse_action(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ActionError("model output contains no JSON action")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ActionError(f"invalid JSON action: {exc}") from exc
    if not isinstance(data, dict) or "action" not in data:
        raise ActionError("action JSON must have an 'action' key")
    return data
