"""Failing test for the practice target project."""

from app import add


def test_add_returns_sum():
    assert add(2, 3) == 5  # FAILS on purpose: add currently returns 6
