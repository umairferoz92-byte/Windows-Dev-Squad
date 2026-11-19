"""Crew roster: the five core roles plus extra roles, names, and size caps."""

from __future__ import annotations

from dataclasses import dataclass

HARD_MAX_AGENTS = 10


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    persona: str
    model_alias: str
    write_scope: str  # "source" | "tests" | "readonly" | "none"


CORE_ROLES = [
    {"role": "coordinator", "persona": "Captain", "model_alias": "planner", "write_scope": "none"},
    {"role": "coder", "persona": "Ironman", "model_alias": "strong", "write_scope": "source"},
    {"role": "tester", "persona": "Tester", "model_alias": "worker", "write_scope": "tests"},
    {"role": "security", "persona": "Batman", "model_alias": "reviewer", "write_scope": "readonly"},
    {"role": "quality", "persona": "Quality", "model_alias": "reviewer", "write_scope": "readonly"},
]

EXTRA_ROLES = ["docs", "performance", "dependencies", "integration", "evals"]

# Pentest specialization roles. These reuse the "security" core role's persona
# when the crew is assembled for an assessment, so a pentest run needs no
# special wiring — just ask the crew to assess a target.
PENTEST_ROLES = ["recon", "scanner", "fingerprint", "findings"]

WRITE_SCOPE_BY_ROLE = {
    "docs": "source",
    "performance": "readonly",
    "dependencies": "source",
    "integration": "tests",
    "evals": "tests",
    "recon": "readonly",
    "scanner": "readonly",
    "fingerprint": "readonly",
    "findings": "readonly",
}


def assemble_pentest_crew(size: int = 4) -> list[AgentSpec]:
    """Build a dedicated pentest crew (recon, scanner, fingerprint, findings)."""
    names = ["recon", "scanner", "fingerprint", "findings"]
    specs = []
    for i in range(max(1, min(int(size), len(names)))):
        role = names[i]
        specs.append(
            AgentSpec(
                name=role,
                role=role,
                persona="Batman",
                model_alias="reviewer",
                write_scope="readonly",
            )
        )
    return specs


def _validate_names(names: list[str]) -> None:
    seen = set()
    for name in names:
        if not name or not name.strip():
            raise ValueError("agent names must be non-empty")
        if name in seen:
            raise ValueError(f"duplicate agent name '{name}'")
        seen.add(name)


def assemble_crew(size: int, names=None, max_agents: int = HARD_MAX_AGENTS) -> list[AgentSpec]:
    """Build a crew of ``size`` agents (capped at max_agents), always covering the
    five core roles; extra agents are assigned file-ownership roles."""
    size = max(1, min(int(size), int(max_agents)))
    names = list(names or [])
    _validate_names(names)

    specs: list[AgentSpec] = []
    for i in range(size):
        if i < len(CORE_ROLES):
            role = CORE_ROLES[i]
        else:
            extra = EXTRA_ROLES[(i - len(CORE_ROLES)) % len(EXTRA_ROLES)]
            role = {
                "role": extra,
                "persona": extra.title(),
                "model_alias": "worker",
                "write_scope": WRITE_SCOPE_BY_ROLE[extra],
            }
        name = names[i] if i < len(names) else f"{role['persona'].lower()}-{i + 1}"
        specs.append(
            AgentSpec(
                name=name,
                role=role["role"],
                persona=role["persona"],
                model_alias=role["model_alias"],
                write_scope=role["write_scope"],
            )
        )
    return specs


def estimate_run_cost(crew: list[AgentSpec], prices, model: str, plan_tokens: int = 2000, code_tokens: int = 8000) -> float | None:
    """Rough dry-run cost estimate (an estimate, not a quote)."""
    price = prices.price_for(model)
    if price is None:
        return None
    total_tokens = plan_tokens + code_tokens * max(1, len(crew) - 1)
    return (total_tokens / 1_000_000) * (price.input_per_mtok + price.output_per_mtok)
