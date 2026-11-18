"""Tests for role -> allowed-model mapping."""

from squad.providers import all_allowed_models, role_allowed_models


def test_all_allowed_models_is_union():
    cfg = {"planner": ["a", "b"], "strong": ["b", "c"], "worker": [], "reviewer": []}
    assert all_allowed_models(cfg) == {"a", "b", "c"}


def test_role_allowed_models():
    cfg = {"worker": ["x"]}
    assert role_allowed_models(cfg, "worker") == {"x"}
    assert role_allowed_models(cfg, "reviewer") == set()
