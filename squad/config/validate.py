"""Refuse unsafe settings (Phase 12 hardening).

Unsafe config fails closed: a report lists every issue, and the CLI refuses to
proceed when any are present.
"""

from __future__ import annotations

KNOWN_PROVIDERS = {
    "openrouter",
    "claude",
    "deepseek",
    "gemini",
    "openai",
    "ollama",
    "lmstudio",
}
BUDGET_MODES = ("economy", "balanced", "max")
HARD_MAX_AGENTS = 10


def _unsafe_scope(path: str) -> bool:
    p = path.replace("\\", "/").strip("/").lower()
    if p == "":
        return True
    if p in ("c:/windows", "windows", "system32", "program files"):
        return True
    if p.startswith("c:/windows/") or p.startswith("/windows/"):
        return True
    return False


def validate_config(repo_config: dict, guard_config: dict, prices: dict | None = None) -> list[str]:
    issues: list[str] = []
    crew = repo_config.get("crew") or {}
    if int(crew.get("size", 5)) > HARD_MAX_AGENTS:
        issues.append(f"crew.size ({crew.get('size')}) exceeds max_agents {HARD_MAX_AGENTS}")
    if int(crew.get("max_agents", HARD_MAX_AGENTS)) > HARD_MAX_AGENTS:
        issues.append(
            f"crew.max_agents ({crew.get('max_agents')}) exceeds the hard cap {HARD_MAX_AGENTS}"
        )

    budget = repo_config.get("budget") or {}
    if budget.get("mode", "balanced") not in BUDGET_MODES:
        issues.append(f"invalid budget mode '{budget.get('mode')}' (use {', '.join(BUDGET_MODES)})")

    providers = (repo_config.get("providers") or {}).get("allowed_providers", [])
    unknown = sorted(set(providers) - KNOWN_PROVIDERS)
    if unknown:
        issues.append(f"unknown provider(s) in allowed_providers: {', '.join(unknown)}")

    scope = (repo_config.get("repo") or {}).get("write_scope") or {}
    for key in ("source", "tests"):
        for path in scope.get(key, []):
            if _unsafe_scope(str(path)):
                issues.append(f"unsafe write_scope.{key} path '{path}'")

    isolation = repo_config.get("isolation") or {}
    min_level = isolation.get("minimum_for_trusted", 2)
    if not isinstance(min_level, int) or min_level not in (0, 1, 2, 3, 4):
        issues.append(f"invalid isolation.minimum_for_trusted '{min_level}'")

    if prices is not None:
        as_of = prices.get("as_of")
        if not as_of:
            issues.append("prices.yaml has no as_of date (models must have prices)")
    return issues


# --- Feature 6: refusal rules (each has a test) --------------------------------
REMOTE_HOSTS_OK = ("127.0.0.1", "localhost")


def _add_refusal(issues, rule, where, fix):
    issues.append(f"[unsafe] {rule} ({where}) -> fix: {fix}")


def validate_unsafe_settings(repo_config: dict, prices: dict | None = None) -> list[str]:
    """Refuse dangerous config that a loosened-and-forgotten setting causes.

    Rules (each maps to a test in tests/config/test_validate.py):
      R1: isolation.level below isolation.minimum_for_trusted (work repo).
      R2: an allowed provider has no budget ceiling anywhere.
      R3: remote access enabled without HTTPS on a non-loopback host.
      R4: a configured model is not on the allowlist (missing from prices).
    """
    issues: list[str] = []
    iso = repo_config.get("isolation") or {}
    if "level" in iso and "minimum_for_trusted" in iso:
        level = iso["level"]
        minimum = iso["minimum_for_trusted"]
        if isinstance(level, int) and isinstance(minimum, int) and level < minimum:
            _add_refusal(issues, f"isolation.level ({level}) is below the repo's "
                                 f"required level ({minimum})",
                         "isolation.level", "raise isolation.level to >= minimum_for_trusted")

    budget = repo_config.get("budget") or {}
    per_provider = (budget.get("per_provider") or {}) if isinstance(budget.get("per_provider"), dict) else {}
    for prov in (repo_config.get("providers") or {}).get("allowed_providers", []):
        has_ceiling = prov in per_provider or budget.get("per_task") or budget.get("per_day")
        if not has_ceiling:
            _add_refusal(issues, f"provider '{prov}' is allowed but has no budget ceiling",
                         f"budget.per_provider.{prov}", "add a per_provider cap for the provider")

    remote = repo_config.get("remote") or {}
    if remote.get("enabled") is True:
        host = remote.get("host", "127.0.0.1")
        if not remote.get("https") and host not in REMOTE_HOSTS_OK:
            _add_refusal(issues, "remote access is enabled without HTTPS on a non-loopback host",
                         "remote.host / remote.https", "bind to 127.0.0.1/localhost or enable https")

    if prices is not None:
        models_cfg = repo_config.get("models") or {}
        known = set(prices.get("models") or {}) or set()
        # prices may map {model: {input:.., output:..}} or {models: [...]}
        if not known and isinstance(prices.get("prices"), dict):
            known = set(prices["prices"])
        for role, models in models_cfg.items():
            if not isinstance(models, list):
                continue
            for m in models:
                if isinstance(m, str) and known and m not in known:
                    _add_refusal(issues, f"model '{m}' ({role}) is not on the allowlist",
                                 f"models.{role}", "add the model to prices.yaml allowlist")
    return issues
