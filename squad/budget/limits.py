"""Budget limits (per call / agent / task / day / month / provider) and modes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BudgetLimits:
    per_call_input_tokens: int = 20000
    per_call_output_tokens: int = 4000
    per_agent: float = 0.0  # 0 = unlimited
    per_task: float = 0.0
    per_day: float = 0.0
    per_month: float = 0.0
    per_provider: dict = field(default_factory=dict)
    mode: str = "balanced"  # economy | balanced | max
    spike_window_seconds: int = 300
    spike_limit: float = 0.0

    @classmethod
    def from_config(cls, data: dict) -> BudgetLimits:
        b = data.get("budget") or {}
        per_call = b.get("per_call") or {}
        return cls(
            per_call_input_tokens=int(per_call.get("input_tokens", 20000)),
            per_call_output_tokens=int(per_call.get("output_tokens", 4000)),
            per_agent=float(b.get("per_agent") or 0),
            per_task=float(b.get("per_task") or 0),
            per_day=float(b.get("per_day") or 0),
            per_month=float(b.get("per_month") or 0),
            per_provider=dict(b.get("per_provider") or {}),
            mode=str(b.get("mode", "balanced")),
            spike_window_seconds=int(b.get("spike_window_seconds", 300)),
            spike_limit=float(b.get("spike_limit") or 0),
        )
