"""The budget layer: refuse over-cap calls before they are sent, warn at 50%/80%,
count unreported usage at worst case, and enforce a spike breaker."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from squad.budget.ledger import Ledger
from squad.budget.limits import BudgetLimits
from squad.budget.prices import PriceTable


class BudgetError(RuntimeError):
    """Raised when a call would pass any budget cap (or is otherwise blocked)."""


@dataclass(frozen=True)
class CallEstimate:
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class BudgetManager:
    def __init__(
        self,
        limits: BudgetLimits,
        prices: PriceTable,
        ledger: Ledger | None = None,
        clock=time.time,
    ):
        self.limits = limits
        self.prices = prices
        self.ledger = ledger
        self._clock = clock
        self._spent_agent: dict[str, float] = defaultdict(float)
        self._spent_provider: dict[str, float] = defaultdict(float)
        self._spent_task = 0.0
        self._spent_day = 0.0
        self._spent_month = 0.0
        self._spike: deque = deque()
        self._warned: set = set()
        self._paused = False
        self.last_warning: str | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def preflight(
        self, agent: str, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> CallEstimate:
        if self._paused:
            raise BudgetError("budget is paused (spike breaker)")

        if input_tokens > self.limits.per_call_input_tokens:
            raise BudgetError(
                f"input tokens {input_tokens} exceed per-call cap "
                f"{self.limits.per_call_input_tokens}"
            )
        if output_tokens > self.limits.per_call_output_tokens:
            raise BudgetError(
                f"output tokens {output_tokens} exceed per-call cap "
                f"{self.limits.per_call_output_tokens}"
            )

        price = self.prices.price_for(model)
        if price is None:
            raise BudgetError(f"unknown model '{model}' (blocked — not in prices.yaml)")

        cost = (input_tokens / 1_000_000) * price.input_per_mtok + (
            output_tokens / 1_000_000
        ) * price.output_per_mtok
        estimate = CallEstimate(model, input_tokens, output_tokens, cost)
        self._check_layers(agent, provider, cost)
        return estimate

    def _check_layers(self, agent: str, provider: str, cost: float) -> None:
        layers = [
            ("per_agent", agent, self._spent_agent[agent], self.limits.per_agent),
            (
                "per_provider",
                provider,
                self._spent_provider[provider],
                self.limits.per_provider.get(provider, 0.0),
            ),
            ("per_task", None, self._spent_task, self.limits.per_task),
            ("per_day", None, self._spent_day, self.limits.per_day),
            ("per_month", None, self._spent_month, self.limits.per_month),
        ]
        for name, key, spent, limit in layers:
            if limit <= 0:
                continue
            total = spent + cost
            if total - limit > 1e-9:
                raise BudgetError(f"{name} budget exceeded: {spent:.6f} + {cost:.6f} > {limit:.6f}")
            ratio = round(total / limit, 6)
            if ratio >= 0.8:
                level = "80%"
            elif ratio >= 0.5:
                level = "50%"
            else:
                level = None
            if level is not None and (name, key, level) not in self._warned:
                self._warned.add((name, key, level))
                self.last_warning = f"{name} at {level} of limit"

    def record(
        self,
        estimate: CallEstimate,
        agent: str,
        provider: str,
        *,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        actual_cost: float | None = None,
        cached_tokens: int = 0,
        run_id: str | None = None,
        now: float | None = None,
    ) -> None:
        # Unreported usage is counted at worst case (the preflight estimate).
        tin = estimate.input_tokens if tokens_in is None else tokens_in
        tout = estimate.output_tokens if tokens_out is None else tokens_out
        cost = estimate.estimated_cost if actual_cost is None else actual_cost

        self._spent_agent[agent] += cost
        self._spent_provider[provider] += cost
        self._spent_task += cost
        self._spent_day += cost
        self._spent_month += cost

        ts = self._clock() if now is None else now
        self._spike.append((ts, cost))
        while self._spike and ts - self._spike[0][0] > self.limits.spike_window_seconds:
            self._spike.popleft()
        if self.limits.spike_limit > 0:
            window_cost = sum(c for _, c in self._spike)
            if window_cost > self.limits.spike_limit:
                self._paused = True
                self.last_warning = "spike limit exceeded — agents paused"

        if self.ledger is not None:
            self.ledger.record(
                run_id, agent, provider, estimate.model, tin, tout, cached_tokens, cost, ts
            )
