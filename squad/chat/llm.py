"""LLM-backed tier of the chatbot: research & advanced reasoning.

Uses the provider resolved by ``squad.providers.factory`` (OpenAI, Anthropic,
OpenRouter, Groq, Gemini, Mistral, Ollama, LM Studio, ...) plus the ``models.worker``
config. Requires a matching API key in the environment/.env; free local servers
(Ollama / LM Studio) need none. The model is treated as a read-only advisor: it
never claims to have executed an action (the offline tier does execution). Raises
``NoKey`` / ``NoModel`` when the prerequisite is missing so the REPL can fall back
to offline answers.
"""

from __future__ import annotations

from dataclasses import dataclass

from squad.providers.base import ProviderError
from squad.providers.models import role_allowed_models

SYSTEM_PROMPT = (
    "You are the Windows Dev Squad assistant — a combined cyber-security expert and "
    "developer coding assistant running inside a live security-and-code terminal tool. "
    "You are a conversation partner, not a one-shot answer box.\n\n"
    "HOW TO INTERACT:\n"
    "- Hold the conversation: remember what the user already said and refer back to it.\n"
    "- If the request is vague or a live scan is needed, ask a short clarifying question "
    " (target, scope, whether it is authorized) instead of guessing.\n"
    "- Recommend concrete `squad` commands (`squad security add-target <t>`, `squad security "
    " nightwing`, `squad review <file>`, `squad chat` tier-1 phrases) and offer to run them.\n"
    "- Be direct and practical: give specific commands, fixes, and reasoning.\n\n"
    "SECURITY:\n"
    "- You are a read-only advisor: you do not run commands yourself, you only explain and "
    " recommend. The user (or the offline tier) executes them.\n"
    "- Any live scanning requires the target to be authorized; Phase C requires interactive "
    " consent. Always flag authorization before recommending a live scan.\n"
    "- Prefer safe, defensive recommendations; never suggest exploiting a system the user "
    " does not own or have permission to test.\n"
)


class NoKey(Exception):
    pass


class NoModel(Exception):
    pass


@dataclass
class LlmReply:
    text: str
    model: str | None = None


def _load_config_models():
    try:
        from squad.checks.config import load_repo_config

        cfg = load_repo_config("squad.yaml")
        return cfg.get("models") or {}
    except Exception:
        return {}


def _resolve_provider(models_cfg: dict):
    """Return (provider_name, api_key, provider) using the factory.

    Raises NoKey when no usable key/provider is configured. A free local
    endpoint (Ollama/LM Studio) is allowed to have an empty key.
    """
    from squad.providers import factory

    name, api_key, spec = factory.resolve_provider(config=models_cfg)
    if not api_key and not spec.free:
        raise NoKey(f"no {spec.key_env} — set it in your repo .env or environment, then run `squad providers test` to confirm.")
    provider = factory.build_provider(name, api_key or "", None)  # allowlist checked per-role
    return name, provider


def _build_questions(prompt: str, history: list[dict] | None = None) -> list[dict]:
    """Build the OpenRouter message list: system + retained history + current turn."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for turn in history:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


def answer(prompt: str, max_tokens: int = 900, history: list[dict] | None = None) -> LlmReply:
    """Answer a research/advanced question through the configured LLM provider,
    carrying the prior conversation for real multi-turn interaction."""
    models_cfg = _load_config_models()
    _name, provider = _resolve_provider(models_cfg)
    worker = sorted(role_allowed_models(models_cfg, "worker"))
    # Free local servers (Ollama) must use a model that server actually hosts —
    # the config's worker model may belong to a cloud provider, so auto-pick an
    # installed Ollama model when this provider is active.
    if _name == "ollama":
        from squad.providers import factory

        installed = factory.ollama_models()
        if installed:
            worker = installed[:1]
    if not worker:
        raise NoModel("no worker model configured in squad.yaml models.worker")
    model = worker[0]

    try:
        resp = provider.chat(model, _build_questions(prompt, history), max_tokens=max_tokens)
    except ProviderError as exc:
        raise NoKey(f"provider error: {exc}") from None
    return LlmReply(text=resp.text.strip(), model=resp.model or model)
