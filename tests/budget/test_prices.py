"""Tests for the price table and unknown-model blocking."""

from datetime import date

from squad.budget import PriceTable

DATA = {
    "as_of": "2026-11-01",
    "models": {
        "openrouter/test/model": {"input": 1.0, "output": 2.0},
    },
}


def test_price_for_known_model():
    table = PriceTable(DATA)
    price = table.price_for("openrouter/test/model")
    assert price is not None
    assert price.input_per_mtok == 1.0
    assert price.output_per_mtok == 2.0


def test_unknown_model_is_blocked():
    table = PriceTable(DATA)
    assert table.price_for("unknown/model") is None
    assert table.is_known("unknown/model") is False


def test_as_of_age_days():
    table = PriceTable(DATA, today=date(2026, 11, 3))
    assert table.as_of_age_days() == 2


def test_missing_as_of_age_is_none():
    table = PriceTable({"models": {}})
    assert table.as_of_age_days() is None
