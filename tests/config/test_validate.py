"""Tests for unsafe-config refusal."""

from squad.config import validate_config


def test_valid_config_no_issues():
    cfg = {
        "crew": {"size": 5, "max_agents": 10},
        "budget": {"mode": "balanced"},
        "providers": {"allowed_providers": ["openrouter"]},
        "repo": {"write_scope": {"source": ["C:/repo/src"]}},
        "isolation": {"minimum_for_trusted": 2},
    }
    assert validate_config(cfg, {}) == []


def test_size_over_cap_flagged():
    issues = validate_config({"crew": {"size": 11}}, {})
    assert any("crew.size" in i for i in issues)


def test_invalid_budget_mode_flagged():
    issues = validate_config({"budget": {"mode": "infinite"}}, {})
    assert any("budget mode" in i for i in issues)


def test_unknown_provider_flagged():
    issues = validate_config({"providers": {"allowed_providers": ["mystery"]}}, {})
    assert any("provider" in i for i in issues)


def test_unsafe_write_scope_flagged():
    cfg = {"repo": {"write_scope": {"source": ["C:/Windows/System32"]}}}
    issues = validate_config(cfg, {})
    assert any("unsafe write_scope" in i for i in issues)


def test_missing_prices_as_of_flagged():
    issues = validate_config({}, {}, {})
    assert any("as_of" in i for i in issues)
