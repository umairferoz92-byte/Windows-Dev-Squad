"""Feature 6: config validation refuses unsafe settings (R1-R4)."""

from squad.config.validate import validate_unsafe_settings

PRICES = {
    "as_of": "2026-01-01",
    "models": {
        "openrouter/openai/gpt-4o-mini": {"input": 0.15, "output": 0.6},
        "openrouter/anthropic/claude-3.5-haiku": {"input": 0.8, "output": 4.0},
    },
}


def test_safe_defaults_need_no_editing():
    cfg = {
        "isolation": {"level": 2, "minimum_for_trusted": 2},
        "providers": {"allowed_providers": ["openrouter"]},
        "budget": {"per_provider": {"openrouter": 5.0}},
        "models": {"worker": ["openrouter/openai/gpt-4o-mini"]},
    }
    assert validate_unsafe_settings(cfg, PRICES) == []


def test_r1_isolation_below_required_flagged():
    cfg = {"isolation": {"level": 1, "minimum_for_trusted": 2}}
    issues = validate_unsafe_settings(cfg, PRICES)
    assert any("below the repo" in i for i in issues)


def test_r2_provider_without_budget_flagged():
    cfg = {
        "providers": {"allowed_providers": ["gemini"]},
        "budget": {"per_provider": {}},  # no ceiling for gemini, no global caps
    }
    issues = validate_unsafe_settings(cfg, PRICES)
    assert any("no budget ceiling" in i for i in issues)


def test_r2_provider_with_budget_ok():
    cfg = {
        "providers": {"allowed_providers": ["gemini"]},
        "budget": {"per_provider": {"gemini": 1.0}},
    }
    assert validate_unsafe_settings(cfg, PRICES) == []


def test_r3_remote_without_https_non_loopback_flagged():
    cfg = {"remote": {"enabled": True, "host": "0.0.0.0", "https": False}}
    issues = validate_unsafe_settings(cfg, PRICES)
    assert any("remote" in i and "HTTPS" in i for i in issues)


def test_r3_remote_loopback_ok():
    cfg = {"remote": {"enabled": True, "host": "127.0.0.1", "https": False}}
    assert validate_unsafe_settings(cfg, PRICES) == []


def test_r4_model_not_on_allowlist_flagged():
    cfg = {"models": {"worker": ["openrouter/evil-unknown-model"]}}
    issues = validate_unsafe_settings(cfg, PRICES)
    assert any("not on the allowlist" in i for i in issues)


def test_r4_known_models_ok():
    cfg = {"models": {"worker": ["openrouter/openai/gpt-4o-mini"]}}
    assert validate_unsafe_settings(cfg, PRICES) == []
