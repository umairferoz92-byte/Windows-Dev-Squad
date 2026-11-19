"""``squad dashboard`` — a blue-themed, interactive, full-terminal TUI dashboard.

Features:
- Pinned header with real-time system/tools/intel state.
- Scrollable transcript area with PageUp/PageDown.
- Rich line editor with left/right cursor movement, backspace, home/end, and up/down command history.
- Built-in interactive menu (`menu`) for entering custom API keys, switching providers, running scans, and self-checks.
- Interactive API key setup command (`setkey <provider> <key>` or `setkey` for guided prompts).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---- Theme: blue -----------------------------------------------------------
BLUE = "#2aa7ff"
BLUE_BRIGHT = "#7cd0ff"
BLUE_DIM = "#1c5a94"
GREEN = "green"
YELLOW = "yellow"
RED = "red"

ASCII_BANNER = r"""
  ____  __ __    ___   __  __  ____  ___   ___
 / __ \/ // /   / _ \ / / / / / __ \/ _ | / _ \
/ /_/ / _  /   / // // /_/ / / /_/ / __ |/ // /
\____/_//_/   /____/ \____/  \____/_/ |_/____/
"""


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------
def _version() -> str:
    try:
        from squad.version import __version__

        return __version__
    except Exception:
        return "?"


def _role() -> str:
    try:
        from squad.roles import current_role

        return current_role()
    except Exception:
        return "owner"


def _tools() -> tuple[int, int, list[tuple[str, bool, str]]]:
    try:
        from squad.tools.manifest import BLUEPRINT_MANIFEST, check_all_tools

        rows = []
        installed = 0
        for s in check_all_tools(BLUEPRINT_MANIFEST):
            installed += 1 if s.installed else 0
            ver = s.version[:28] if s.installed else "missing"
            rows.append((s.display, s.installed, ver))
        return installed, len(rows), rows
    except Exception:
        return 0, 0, []


def _intel() -> tuple[int, int]:
    try:
        from squad.intel import RealTimeIntelEngine

        f = RealTimeIntelEngine().intel
        return len(f.security_advisories), len(f.coding_practices)
    except Exception:
        return 0, 0


def _scans() -> tuple[int, str]:
    try:
        from squad.store.history import ScanStore

        s = ScanStore().status_summary()
        return s["total_runs"], s["latest_target"] or "none yet"
    except Exception:
        return 0, "none yet"


def _missing_keys() -> list[str]:
    from squad.providers import factory

    name, api_key, _spec = factory.resolve_provider()
    if api_key or _spec.free:
        return []
    return [f"API key for provider '{name}' ({_spec.key_env})"]


def save_api_key(provider_name: str, key_value: str) -> tuple[bool, str]:
    """Save an API key to local .env and update os.environ live."""
    from squad.config.data import data_dir
    from squad.providers import factory

    provider_name = provider_name.strip().lower()
    key_env = factory.provider_key_env(provider_name)
    if not key_env:
        if provider_name.endswith("_KEY") or provider_name.endswith("_TOKEN"):
            key_env = provider_name.upper()
        else:
            key_env = f"{provider_name.upper()}_API_KEY"

    key_value = key_value.strip()
    if not key_value:
        return False, "Key value cannot be empty."

    # Update current runtime environment
    os.environ[key_env] = key_value
    os.environ["SQUAD_LLM_PROVIDER"] = provider_name

    # Write to local .env in data_dir & CWD
    written = []
    for env_path in [Path(".env"), data_dir() / ".env"]:
        try:
            env_path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith(f"{key_env}=") or line.startswith("SQUAD_LLM_PROVIDER="):
                        continue
                    lines.append(line)
            lines.append(f"{key_env}={key_value}")
            lines.append(f"SQUAD_LLM_PROVIDER={provider_name}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            written.append(str(env_path))
        except Exception:
            pass

    return (
        True,
        f"Saved {key_env} and set active provider to '{provider_name}' ({', '.join(written)}).",
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _banner() -> Text:
    return Text(ASCII_BANNER, style=BLUE_BRIGHT)


def _session_panel(role: str, ver: str) -> Panel:
    from squad.providers import factory

    p_name, p_key, p_spec = factory.resolve_provider()
    model_str = f"{p_name} ({'free' if p_spec.free else ('key set' if p_key else 'no key')})"

    table = Table(box=box.SIMPLE, show_header=False, border_style=BLUE_DIM)
    table.add_column(style=BLUE, width=12)
    table.add_column(style="white")
    table.add_row("Agent", "SQUAD / cyber & dev assistant")
    table.add_row("Version", f"v{ver}")
    table.add_row("Role", role)
    table.add_row("Provider", model_str)
    table.add_row("Workdir", os.getcwd())
    table.add_row("Session", "interactive TUI")
    return Panel(table, title="Session", border_style=BLUE_DIM, title_align="left")


def _tools_panel(rows: list[tuple[str, bool, str]]) -> Panel:
    t = Table(box=box.SIMPLE, border_style=BLUE_DIM, header_style=BLUE_BRIGHT)
    t.add_column("Tool")
    t.add_column("Status", justify="center", width=10)
    t.add_column("Version")
    for name, ok, ver in rows:
        t.add_row(name, "[green]✔ ready[/]" if ok else "[red]✖ missing[/]", ver)
    return Panel(t, title="Security Tools (12)", border_style=BLUE_DIM, title_align="left")


def _intel_panel(adv: int, prac: int, scans: int, latest: str) -> Panel:
    t = Table(box=box.SIMPLE, show_header=False, border_style=BLUE_DIM)
    t.add_column(style=BLUE, width=20)
    t.add_column(style="white")
    t.add_row("Threat advisories", str(adv))
    t.add_row("Coding practices", str(prac))
    t.add_row("Past scan runs", str(scans))
    t.add_row("Latest target", latest)
    return Panel(t, title="Live State", border_style=BLUE_DIM, title_align="left")


def _warnings(missing_keys: list[str], missing_tools: int) -> Panel:
    lines = []
    if missing_keys:
        lines.append(Text("⚠ Some LLM capabilities disabled (missing keys):", style=YELLOW))
        for k in missing_keys:
            lines.append(Text(f"   • {k} — type `setkey` to configure", style="dim"))
    if missing_tools:
        lines.append(
            Text(
                f"⚠ {missing_tools}/12 security tools missing — run `check tools` to install.",
                style=YELLOW,
            )
        )
    if not lines:
        lines.append(Text("✓ All configured providers and security tools ready.", style=GREEN))
    return Panel(Group(*lines), border_style=BLUE_DIM)


def _header() -> Panel:
    ver = _version()
    role = _role()
    installed, total, rows = _tools()
    adv, prac = _intel()
    scans, latest = _scans()
    missing_keys = _missing_keys()

    left = Group(
        _session_panel(role, ver),
        "",
        _intel_panel(adv, prac, scans, latest),
    )
    right = _tools_panel(rows)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(ratio=5)
    grid.add_row(left, right)

    body = Group(
        _banner(),
        Panel(grid, border_style=BLUE, padding=(0, 1)),
        _warnings(missing_keys, total - installed),
    )
    return Panel(body, border_style=BLUE, title="Windows Dev Squad — Interactive TUI", title_align="left")


def build_dashboard() -> Group:
    ver = _version()
    role = _role()
    installed, total, rows = _tools()
    adv, prac = _intel()
    scans, latest = _scans()
    missing_keys = _missing_keys()

    left = Group(
        _session_panel(role, ver),
        "",
        _intel_panel(adv, prac, scans, latest),
    )
    right = _tools_panel(rows)

    grid = Table.grid(expand=True)
    grid.add_column(ratio=3)
    grid.add_column(ratio=5)
    grid.add_row(left, right)

    summary = Text(
        f"  {total} tools · {adv} advisories · {prac} practices · run `squad chat` for interactive help  ",
        style=BLUE_DIM,
    )

    prompt = Text("  squad> ", style=BLUE_BRIGHT) + Text("type a command or `help`", style="dim")

    return Group(
        _banner(),
        Panel(grid, border_style=BLUE, padding=(0, 1)),
        _warnings(missing_keys, total - installed),
        "",
        summary,
        prompt,
    )


HELP_TEXT = """\
Available Commands:
  menu                   Open interactive action menu
  setkey [provider] [key] Insert/update custom LLM API key live (e.g. `setkey openai sk-...`)
  review <file>          Security & code quality review
  testgen <file>         Generate test suite for file
  refactor <file>        Modernize and clean code
  scan <target>          Run Nightwing recon & static scan
  search <topic>         Search threat advisories & practices
  doctor                 Run system environment doctor check
  check tools            Verify & optionally install missing pentest tools
  exit / quit            Exit TUI"""

MENU_TEXT = """\
=== Interactive Menu Options ===
  1. Insert Custom API Key (`setkey`)
  2. Use Free Local Ollama Models (`setkey ollama free`)
  3. Run Code Security Review
  4. Generate Tests
  5. System Doctor Check
  6. Check/Install Pentest Tools
  7. Show Full Command Help
Type the number (1-7) or command name above."""


class LineEditor:
    """Rich terminal line editor with cursor movement, backspace, and history."""

    def __init__(self) -> None:
        self.buf: list[str] = []
        self.pos: int = 0
        self.history: list[str] = []
        self.hist_idx: int = 0

    def insert(self, char: str) -> None:
        self.buf.insert(self.pos, char)
        self.pos += 1

    def backspace(self) -> None:
        if self.pos > 0:
            self.pos -= 1
            self.buf.pop(self.pos)

    def delete(self) -> None:
        if self.pos < len(self.buf):
            self.buf.pop(self.pos)

    def move_left(self) -> None:
        if self.pos > 0:
            self.pos -= 1

    def move_right(self) -> None:
        if self.pos < len(self.buf):
            self.pos += 1

    def move_home(self) -> None:
        self.pos = 0

    def move_end(self) -> None:
        self.pos = len(self.buf)

    def history_up(self) -> None:
        if not self.history:
            return
        if self.hist_idx > 0:
            self.hist_idx -= 1
            line = self.history[self.hist_idx]
            self.buf = list(line)
            self.pos = len(self.buf)

    def history_down(self) -> None:
        if not self.history:
            return
        if self.hist_idx < len(self.history) - 1:
            self.hist_idx += 1
            line = self.history[self.hist_idx]
            self.buf = list(line)
            self.pos = len(self.buf)
        else:
            self.hist_idx = len(self.history)
            self.buf.clear()
            self.pos = 0

    def submit(self) -> str:
        line = "".join(self.buf).strip()
        if line:
            if not self.history or self.history[-1] != line:
                self.history.append(line)
            self.hist_idx = len(self.history)
        self.buf.clear()
        self.pos = 0
        return line

    def render_prompt(self, prompt_mode: str = "command") -> Text:
        prompt_str = "squad> "
        if prompt_mode == "setkey_provider":
            prompt_str = "provider> "
        elif prompt_mode == "setkey_value":
            prompt_str = "key> "

        prompt = Text(prompt_str, style=BLUE_BRIGHT)
        if not self.buf:
            placeholder = "type a command, 'menu', or 'setkey'"
            if prompt_mode == "setkey_provider":
                placeholder = "e.g. openai, openrouter, anthropic, groq"
            elif prompt_mode == "setkey_value":
                placeholder = "paste your API key value here"
            prompt.append(placeholder, style="dim")
            return prompt

        before = "".join(self.buf[: self.pos])
        cursor = self.buf[self.pos] if self.pos < len(self.buf) else " "
        after = "".join(self.buf[self.pos + 1 :])

        prompt.append(before, style="white")
        prompt.append(cursor, style="reverse white")
        if self.pos < len(self.buf):
            prompt.append(after, style="white")
        return prompt


def dashboard_command() -> None:
    """Run full-screen interactive TUI with arrow keys, scrolling, and key setup."""
    console = Console()
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=min(32, max(16, (console.height or 40) - 14))),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )

    transcript: list[Text] = [
        Text(
            "Welcome to Windows Dev Squad! Use Up/Down for command history, PgUp/PgDn to scroll.",
            style=BLUE_DIM,
        ),
        Text(
            "Type `menu` for options, or `setkey <provider> <key>` to configure an API key live.",
            style=BLUE_BRIGHT,
        ),
    ]

    editor = LineEditor()
    prompt_mode = "command"
    pending_provider = ""
    dirty = True

    last_header_update = 0.0
    header_panel = _header()

    # Scroll state: `scroll` = number of lines hidden from the BOTTOM of the
    # transcript. 0 == at the newest output.
    scroll = 0
    body_height = max(6, (console.height or 40) - 38)

    def render() -> None:
        nonlocal last_header_update, header_panel, scroll, body_height

        body_height = max(6, (console.height or 40) - 38)

        # Only refresh header every 5 seconds to reduce I/O
        now = time.time()
        if now - last_header_update > 5.0:
            header_panel = _header()
            last_header_update = now

        layout["header"].update(header_panel)

        if scroll >= len(transcript):
            scroll = max(0, len(transcript) - 1)

        start = max(0, len(transcript) - scroll - body_height)
        end = max(0, len(transcript) - scroll)
        visible_lines = transcript[start:end] if end > 0 else transcript

        body_table = Table.grid(expand=True)
        body_table.add_column()
        for line in visible_lines:
            body_table.add_row(line)

        title = f"Transcript (scroll: {scroll} from bottom)" if scroll else "Transcript"
        layout["body"].update(Panel(body_table, title=title, border_style=BLUE_DIM))
        layout["footer"].update(Panel(editor.render_prompt(prompt_mode), border_style=BLUE_DIM))

    def append_transcript(msg: str | Text, style: str = "white") -> None:
        nonlocal scroll
        scroll = 0
        if isinstance(msg, str):
            for line in msg.splitlines():
                transcript.append(Text(line, style=style))
        else:
            transcript.append(msg)

    def process_command(cmd: str) -> bool:
        nonlocal prompt_mode, pending_provider

        if prompt_mode == "setkey_provider":
            pending_provider = cmd.strip()
            prompt_mode = "setkey_value"
            append_transcript(f"Enter API Key value for '{pending_provider}':", style=BLUE_BRIGHT)
            return False

        if prompt_mode == "setkey_value":
            ok, msg = save_api_key(pending_provider, cmd)
            append_transcript(msg, style=GREEN if ok else RED)
            prompt_mode = "command"
            return False

        # Menu selections
        if cmd == "1":
            prompt_mode = "setkey_provider"
            append_transcript(
                "Enter provider name (e.g. openai, openrouter, anthropic, groq, gemini):",
                style=BLUE_BRIGHT,
            )
            return False
        elif cmd == "2":
            ok, msg = save_api_key("ollama", "free")
            append_transcript(msg, style=GREEN)
            return False
        elif cmd == "3":
            cmd = "review"
        elif cmd == "4":
            cmd = "generate tests"
        elif cmd == "5":
            cmd = "doctor"
        elif cmd == "6":
            cmd = "check tools"
        elif cmd == "7":
            cmd = "help"

        if cmd.lower() in ("exit", "quit"):
            append_transcript("Exiting TUI...", style=BLUE_DIM)
            return True

        if cmd.lower() == "menu":
            append_transcript(MENU_TEXT, style=BLUE_BRIGHT)
            return False

        if cmd.lower() == "help":
            append_transcript(HELP_TEXT, style="white")
            return False

        if cmd.lower().startswith("setkey") or cmd.lower().startswith("key"):
            parts = cmd.split(maxsplit=2)
            if len(parts) == 3:
                ok, msg = save_api_key(parts[1], parts[2])
                append_transcript(msg, style=GREEN if ok else RED)
            else:
                prompt_mode = "setkey_provider"
                append_transcript(
                    "Enter provider name (e.g. openai, openrouter, anthropic, groq):",
                    style=BLUE_BRIGHT,
                )
            return False

        append_transcript(f"squad> {cmd}", style=BLUE_BRIGHT)
        try:
            from squad.chat import offline

            intent = offline.parse(cmd)
            if intent.kind == "llm":
                append_transcript(_research(cmd), style="white")
            else:
                out = _execute(intent)
                append_transcript(out, style="white")
        except Exception as exc:
            append_transcript(f"Error: {exc}", style=RED)

        return False

    try:
        import msvcrt

        from rich.live import Live

        with Live(layout, console=console, screen=True, refresh_per_second=25) as live:
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    dirty = True
                    if ch in ("\xe0", "\x00"):
                        # Extended/arrow keys are sent as a TWO-BYTE sequence
                        # (\xe0 or \x00, then a virtual-key code). A touchpad
                        # scroll can split these bytes across event frames, so
                        # read the second byte with a short bounded wait. If it
                        # never arrives, swallow the lone prefix rather than
                        # letting its partner byte leak in as a typed letter.
                        vk = None
                        deadline = time.monotonic() + 0.008
                        while time.monotonic() < deadline:
                            if msvcrt.kbhit():
                                vk = msvcrt.getwch()
                                break
                            time.sleep(0.0004)
                        if vk is None:
                            continue
                        if vk == "K":  # Left Arrow
                            editor.move_left()
                        elif vk == "M":  # Right Arrow
                            editor.move_right()
                        elif vk == "H":  # Up Arrow
                            if scroll > 0 or len(transcript) > body_height:
                                scroll = min(len(transcript) - 1, scroll + 1)  # scroll up
                            else:
                                editor.history_up()
                        elif vk == "P":  # Down Arrow
                            if scroll > 0:
                                scroll = max(0, scroll - 1)  # scroll back down
                            else:
                                editor.history_down()
                        elif vk == "G":  # Home
                            editor.move_home()
                        elif vk == "O":  # End
                            editor.move_end()
                        elif vk == "S":  # Delete
                            editor.delete()
                        elif vk == "I":  # PageUp
                            scroll = min(len(transcript) - 1, scroll + body_height)
                        elif vk == "Q":  # PageDown
                            scroll = max(0, scroll - body_height)
                    elif ch in ("\r", "\n"):
                        cmd = editor.submit()
                        if cmd:
                            should_exit = process_command(cmd)
                            if should_exit:
                                break
                    elif ch in ("\x08", "\x7f"):  # Backspace
                        editor.backspace()
                    elif ch == "\x03":  # Ctrl+C
                        break
                    else:
                        editor.insert(ch)

                if dirty:
                    render()
                    live.update(layout)
                    dirty = False

                time.sleep(0.015)

    except (KeyboardInterrupt, ImportError):
        console.print("\nExiting TUI.")


def _execute(intent) -> str:
    """Run an offline action intent; returns the output text."""
    from squad.chat import offline

    cmd = intent.cmd or []
    try:
        out = offline.run_command(cmd)
        return (out or "(no output)").strip()
    except Exception as exc:
        return f"[error] {type(exc).__name__}: {exc}"


def _research(prompt: str) -> str:
    """LLM-backed research with graceful offline fallback (offline KB, then intel search)."""
    from squad.chat import llm as llm_tier
    from squad.chat.offline import run_command

    try:
        reply = llm_tier.answer(prompt)
        prefix = f"[llm/{reply.model}] " if reply.model else "[llm] "
        return prefix + reply.text
    except (llm_tier.NoKey, llm_tier.NoModel):
        from squad.chat import offline_answer

        kb = offline_answer.lookup(prompt)
        if kb:
            return kb + "\n[note] offline answer — no API key needed. Use `setkey` to add one."
        q = " ".join(
            w
            for w in prompt.split()
            if w.lower()
            not in {
                "what",
                "is",
                "are",
                "the",
                "a",
                "an",
                "how",
                "why",
                "to",
                "me",
                "my",
                "in",
                "on",
                "for",
                "and",
                "or",
                "with",
                "i",
                "can",
                "you",
                "tell",
                "about",
                "explain",
                "give",
                "do",
                "does",
            }
        )[:80]
        out = run_command(["intel", "search", q])
        return out + "\n[note] set an LLM API key (type `setkey`) to unlock full LLM research."
    except Exception as exc:
        q = " ".join(
            w
            for w in prompt.split()
            if w.lower()
            not in {
                "what",
                "is",
                "are",
                "the",
                "a",
                "an",
                "how",
                "why",
                "to",
                "me",
                "my",
                "in",
                "on",
                "for",
                "and",
                "or",
                "with",
                "i",
                "can",
                "you",
                "tell",
                "about",
                "explain",
                "give",
                "do",
                "does",
            }
        )[:80]
        out = run_command(["intel", "search", q])
        return out + f"\n[note] LLM unavailable ({type(exc).__name__}); fell back to offline intel."


def main() -> None:
    dashboard_command()


if __name__ == "__main__":
    main()
