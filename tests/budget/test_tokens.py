"""Tests for conservative token estimation."""

from squad.budget import estimate_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_short_is_at_least_one():
    assert estimate_tokens("a") == 1


def test_ceil_division_by_three():
    assert estimate_tokens("abc") == 1  # 3 -> 1
    assert estimate_tokens("abcd") == 2  # 4 -> 2
    assert estimate_tokens("123456") == 2  # 6 -> 2
    assert estimate_tokens("1234567") == 3  # 7 -> 3
