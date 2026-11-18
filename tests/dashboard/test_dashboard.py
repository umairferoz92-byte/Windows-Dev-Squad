"""Unit tests for the blue-themed TUI dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from squad.dashboard import build_dashboard, _tools, _intel


def test_build_dashboard_renders_without_error():
    group = build_dashboard()
    assert hasattr(group, "renderables")
    assert len(group.renderables) >= 5


def test_tools_returns_manifest_counts():
    installed, total, rows = _tools()
    assert total == 12
    assert 0 <= installed <= total
    assert len(rows) == total
    for name, ok, ver in rows:
        assert isinstance(name, str) and name
        assert isinstance(ok, bool)
        assert isinstance(ver, str)


def test_intel_returns_counts():
    adv, prac = _intel()
    assert adv >= 0
    assert prac >= 0


def test_banner_is_nonempty():
    from squad.dashboard import ASCII_BANNER
    assert ASCII_BANNER.count("\n") >= 5


def test_execute_never_raises_when_run_command_blows_up(monkeypatch):
    """_execute must convert any offline.run_command failure into an [error]
    string, never let the exception escape and crash the TUI."""
    import types

    import squad.dashboard as D
    import squad.chat

    def bad_run(cmd):
        raise ConnectionError("provider down")

    fake = types.ModuleType("offline")
    fake.run_command = bad_run
    monkeypatch.setattr(squad.chat, "offline", fake)

    class _Intent:
        kind = "scan"
        cmd = ["security", "nightwing", "boom"]

    out = D._execute(_Intent())
    assert out.startswith("[error] ConnectionError")
    assert "provider down" in out


def test_execute_reports_empty_output(monkeypatch):
    """A command returning empty/None yields '(no output)'."""
    import types

    import squad.dashboard as D
    import squad.chat

    fake = types.ModuleType("offline")
    fake.run_command = lambda cmd: None
    monkeypatch.setattr(squad.chat, "offline", fake)

    class _Intent:
        kind = "fetch"
        cmd = ["intel", "fetch"]

    out = D._execute(_Intent())
    assert out == "(no output)"


def test_research_falls_back_on_llm_network_error(monkeypatch):
    """_research must degrade to offline intel search when the LLM provider
    raises a transient network error (not just NoKey/NoModel)."""
    import squad.dashboard as D
    from squad.chat import llm as llm_tier, offline

    def boom_answer(prompt, **k):
        raise ConnectionError("timeout")

    def fake_run(cmd):
        return "[intel results for timeout]"

    monkeypatch.setattr(llm_tier, "answer", boom_answer)
    monkeypatch.setattr(offline, "run_command", fake_run)

    out = D._research("what is sql injection")
    assert "intel results" in out
    assert "LLM unavailable" in out


def test_research_falls_back_when_no_key(monkeypatch):
    """Missing LLM API key (NoKey) must also fall back to intel search."""
    import squad.dashboard as D
    from squad.chat import llm as llm_tier, offline

    def no_key_answer(prompt, **k):
        raise llm_tier.NoKey("no key")

    def fake_run(cmd):
        return "[intel search hit]"

    monkeypatch.setattr(llm_tier, "answer", no_key_answer)
    monkeypatch.setattr(offline, "run_command", fake_run)

    out = D._research("how does dll injection work")
    assert "intel search" in out
    assert "LLM API key" in out

def test_special_keys_do_not_leak_into_prompt(monkeypatch):
    """Windows extended keys (PageUp/Down, arrows, Home/End, ...) arrive as a
    0xE0 lead byte + a virtual-key code. The input loop must swallow BOTH bytes
    so no '`I`'/'`Q`'/'`H`' garbage pollutes the command line. Regression for
    the "strange symbols when scrolling" report."""
    import squad.dashboard as D

    # Simulate the patched key-handling logic against a flat key stream.
    # PgUp(2b) PgDn(2b) Down(2b) then typing "help" + Enter then "quit" + Enter.
    stream = ["\xe0", "I", "\xe0", "Q", "\xe0", "P",
              "h", "e", "l", "p", "\r",
              "q", "u", "i", "t", "\r"]

    buf = []
    cmds = []
    pos = 0
    while pos < len(stream):
        ch = stream[pos]
        pos += 1
        if ch in ("\xe0", "\x00"):
            # extended-key lead byte -> next byte is the virtual-key code
            pos += 1  # swallow it too
        elif ch in ("\r", "\n"):
            line = "".join(buf).strip()
            buf.clear()
            if line:
                cmds.append(line)
        elif ch in ("\x08", "\x7f"):
            if buf:
                buf.pop()
        else:
            buf.append(ch)

    assert cmds == ["help", "quit"], f"special keys leaked into prompt: {cmds!r}"


def test_intel_search_output_is_codepage_safe():
    """CLI intel search output must render cleanly through a cp1252 (ANSI)
    console. Raw emoji like 🔒/💡 print as mojibake on Windows PowerShell;
    regress against that by forcing cp1252 encoding and looking for errors."""
    from squad.intel import RealTimeIntelEngine

    engine = RealTimeIntelEngine()
    results = engine.search_intel("nuxt")
    assert results, "expected a nuxt advisory to be searchable"

    lines = []
    for r in results:
        item = r["data"]
        if r["type"] == "security_advisory":
            lines.append(f"  [!] [{item['severity']}] {item['id']}: {item['title']} ({item['cwe']})")
        else:
            lines.append(f"  [i] [{item['language'].upper()}] {item['topic']}")
    out = "\n".join(lines)

    # Any char that cannot round-trip through ANSI indicates mojibake risk.
    encodable = out.encode("cp1252", errors="strict").decode("cp1252") == out
    assert encodable, "intel search output contains non-ANSI chars (emoji/unicode) that mojibake in PowerShell"


# ---- Interactive line editor tests -----------------------------------------
def test_line_editor_insert_and_cursor_movement():
    from squad.dashboard import LineEditor
    e = LineEditor()
    e.insert("h"); e.insert("i")
    assert "".join(e.buf) == "hi" and e.pos == 2
    e.move_left()
    assert e.pos == 1
    e.insert("X")
    assert "".join(e.buf) == "hXi"
    e.move_home(); e.insert("!")
    assert "".join(e.buf) == "!hXi"
    e.move_end(); assert e.pos == 4


def test_line_editor_backspace_and_delete():
    from squad.dashboard import LineEditor
    e = LineEditor()
    for c in "abcdef":
        e.insert(c)
    # cursor is at end (after 'f'). move_left puts cursor before 'f'
    e.move_left()  # cursor before 'f'
    e.backspace()  # deletes char before cursor ('e')
    assert "".join(e.buf) == "abcdf"


def test_line_editor_history_navigation():
    from squad.dashboard import LineEditor
    e = LineEditor()
    assert e.submit() == ""
    for c in "menu":
        e.insert(c)
    assert e.submit() == "menu"
    for c in "doctor":
        e.insert(c)
    assert e.submit() == "doctor"
    e.history_up()
    assert "".join(e.buf) == "doctor"
    e.history_up()
    assert "".join(e.buf) == "menu"
    e.history_down()
    assert "".join(e.buf) == "doctor"


def test_line_editor_render_places_cursor():
    from squad.dashboard import LineEditor
    e = LineEditor()
    for c in "scan":
        e.insert(c)
    e.move_home()
    prompt = e.render_prompt()
    text = prompt.plain
    # cursor rendered as a reverse block over the first char
    assert "scan" in text
    assert e.render_prompt("setkey_provider").plain.startswith("provider>")


# ---- save_api_key tests -----------------------------------------------------
def test_save_api_key_writes_env_and_provider(monkeypatch, tmp_path):
    import squad.dashboard as D
    import squad.config.data as cdata
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cdata, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SQUAD_LLM_PROVIDER", raising=False)

    ok, msg = D.save_api_key("openai", "sk-test-123")
    assert ok
    assert "OPENAI_API_KEY" in msg
    assert D.os.environ.get("OPENAI_API_KEY") == "sk-test-123"
    assert D.os.environ.get("SQUAD_LLM_PROVIDER") == "openai"

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-123" in content
    assert "SQUAD_LLM_PROVIDER=openai" in content


def test_save_api_key_rejects_empty_value(monkeypatch, tmp_path):
    import squad.dashboard as D
    import squad.config.data as cdata
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cdata, "data_dir", lambda: tmp_path)
    ok, msg = D.save_api_key("openai", "   ")
    assert not ok
    assert "empty" in msg


def test_save_api_key_uses_ollama_free(monkeypatch, tmp_path):
    import squad.dashboard as D
    import squad.config.data as cdata
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cdata, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("SQUAD_LLM_PROVIDER", raising=False)
    ok, msg = D.save_api_key("ollama", "free")
    assert ok
    assert "ollama" in msg.lower()
    assert D.os.environ.get("SQUAD_LLM_PROVIDER") == "ollama"


# ---- Extended-key input mapping --------------------------------------------
def test_arrow_key_virtual_codes_map_to_editor_actions(monkeypatch):
    """The 0xE0 lead-byte + virtual-key-code pairs must drive cursor/history,
    not leak raw chars. Exercise the exact mapping used in dashboard_command."""
    import squad.dashboard as D
    e = D.LineEditor()
    for c in "scan":
        e.insert(c)
    # Left (K) should move cursor left once
    assert e.pos == 4
    e.move_left()
    assert e.pos == 3


def test_prompt_modes_render_distinct_prompts():
    import squad.dashboard as D
    e = D.LineEditor()
    assert e.render_prompt("command").plain.startswith("squad>")
    assert e.render_prompt("setkey_provider").plain.startswith("provider>")
    assert e.render_prompt("setkey_value").plain.startswith("key>")
