"""Conservative token estimation (no tokenizer package): characters ÷ 3, rounded up."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count conservatively as ceil(len(text) / 3), minimum 1."""
    if not text:
        return 0
    return max(1, (len(text) + 2) // 3)
