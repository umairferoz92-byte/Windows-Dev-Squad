"""Model prices from prices.yaml. Unknown models are blocked (never hard-coded)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float  # USD per 1M input tokens
    output_per_mtok: float  # USD per 1M output tokens


def _parse_date(value, today: date) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


class PriceTable:
    def __init__(self, data: dict | None = None, today: date | None = None):
        data = data or {}
        self._today = today or date.today()
        self.as_of = _parse_date(data.get("as_of"), self._today)
        self.models: dict[str, ModelPrice] = {}
        for name, entry in (data.get("models") or {}).items():
            self.models[name] = ModelPrice(
                float(entry.get("input", 0.0)),
                float(entry.get("output", 0.0)),
            )

    def price_for(self, model: str) -> ModelPrice | None:
        return self.models.get(model)

    def is_known(self, model: str) -> bool:
        return model in self.models

    def as_of_age_days(self) -> int | None:
        if self.as_of is None:
            return None
        return (self._today - self.as_of).days
