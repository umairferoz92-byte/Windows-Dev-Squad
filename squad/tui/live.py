"""Live TUI rendering (rich): one card per agent, plus approval prompts.

The render functions are pure (they build rich output to text), so they are
testable headless; the live-refresh loop is a thin layer on top.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass(frozen=True)
class AgentCard:
    name: str
    role: str
    step: int = 0
    status: str = "idle"
    cost: float = 0.0
    budget: float = 0.0
    files: tuple[str, ...] = ()


def render_live(cards: list[AgentCard], width: int = 120) -> str:
    table = Table(title="squad — live", show_header=True)
    table.add_column("Agent")
    table.add_column("Role")
    table.add_column("Step")
    table.add_column("Status")
    table.add_column("Cost / Budget")
    table.add_column("Files touched")
    for card in cards:
        budget = f"${card.cost:.6f} / ${card.budget:.6f}" if card.budget else f"${card.cost:.6f}"
        table.add_row(
            card.name,
            card.role,
            str(card.step),
            card.status,
            budget,
            ", ".join(card.files),
        )
    console = Console(record=True, width=width)
    console.print(table)
    return console.export_text()


def render_approval(tool: str, args: dict, cwd: str, reason: str, width: int = 100) -> str:
    console = Console(record=True, width=width)
    console.print(
        Panel(
            f"tool: {tool}\nfolder: {cwd}\nargs: {args}\nreason: {reason}",
            title="Approval required (expires in 5 minutes)",
        )
    )
    return console.export_text()


def live_refresh(
    poll,
    *,
    interval: float = 1.0,
    max_iterations: int = 0,
    width: int = 120,
    on_render=None,
):
    """Run a live-refresh loop: repeatedly poll for agent-card state and
    repaint the rich view.

    ``poll`` is a zero-arg callable returning a list of AgentCard (or a list
    of dicts compatible with AgentCard). ``on_render`` (optional) receives each
    rendered frame so a caller can write it to a file or feed the gateway.

    Stops after ``max_iterations`` (0 = run until Ctrl-C / StopIteration from
    poll). Raises ``StopIteration`` out of poll to end the loop.
    """
    import time
    from rich.live import Live

    def _to_cards(raw):
        cards = []
        for item in raw or []:
            if isinstance(item, AgentCard):
                cards.append(item)
            elif isinstance(item, dict):
                cards.append(
                    AgentCard(
                        name=item.get("name", "?"),
                        role=item.get("role", ""),
                        step=int(item.get("step", 0)),
                        status=item.get("status", "idle"),
                        cost=float(item.get("cost", 0.0)),
                        budget=float(item.get("budget", 0.0)),
                        files=tuple(item.get("files", [])),
                    )
                )
        return cards

    iteration = 0
    with Live(refresh_per_second=1.0 / max(interval, 0.1)) as live:
        while max_iterations == 0 or iteration < max_iterations:
            raw = poll()
            cards = _to_cards(raw)
            frame = render_live(cards, width=width)
            live.update(frame, refresh=True)
            if on_render:
                on_render(frame, cards)
            iteration += 1
            time.sleep(interval)
