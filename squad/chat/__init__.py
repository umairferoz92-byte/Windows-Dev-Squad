"""``squad chat`` — a two-tier terminal chatbot.

Tier 1 (offline): rule-based intent parsing turns natural language into the real
``squad`` subcommands and runs them. No API key, works offline.
Tier 2 (LLM): research/advanced questions route to the configured OpenRouter
provider (``OPENROUTER_API_KEY`` + ``models.worker`` in squad.yaml). The model is
a read-only advisor — it recommends, it never executes.
"""
from __future__ import annotations

import shlex
from typing import Callable, Optional

from squad.chat import llm as llm_tier
from squad.chat import memory as mem
from squad.chat import offline

HELP_TEXT = """\
Windows Dev Squad chat — ask in plain English. Examples:

  review C:/path/to/file.py        review code (quality + security + intel)
  generate tests for utils.py      write unit tests
  refactor legacy.py               modernize code
  scan http://example.com          run a Nightwing scan (phase A+B)
  scan <t> repo C:/my-app          scan with a local repo for static analysis
  fetch intel / search CWE-89      refresh / query live intelligence
  security status / history        current & past scans
  doctor                           environment self-check
  check tools                      list installed security tools
  export <run_id> as csv           export findings
  help                             this message
  exit / quit                      leave the chat

Research / advanced (LLM tier, needs any configured LLM API key):
  what is SQL injection / explain TLS / how do I harden my API ...

Try one of those above.
"""


def _confirm(prompt: str) -> bool:
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes", "run", "go")


def _handle(intent: offline.Intent, history: list[dict] | None = None) -> str:
    if intent.kind == "help":
        return HELP_TEXT
    if intent.kind == "quit":
        return ""
    if intent.kind == "interactive":
        # A genuinely interactive command the agent can walk the user through.
        return _handle_interactive(intent)
    if intent.kind == "action":
        cmd = intent.cmd or []
        # Interactive confirmations live inside these commands, so just run them.
        print(f"\n[chat] running: python -m squad {' '.join(shlex.quote(c) for c in cmd)}\n")
        out = offline.run_command(cmd)
        if intent.note:
            out += f"\n\n[chat] {intent.note}"
        return out
    if intent.kind == "llm":
        # The rule parser reached the LLM catch-all. If the TF intent classifier
        # confidently knows this is a real squad action, route it there instead
        # of guessing an LLM answer.
        routed = _try_classifier_route(intent.note)
        if routed is not None:
            cmd = routed
            print(f"\n[chat] (intent classifier) running: python -m squad {' '.join(shlex.quote(c) for c in cmd)}\n")
            return offline.run_command(cmd)
        # Code-security vetting: the user pasted a snippet to check for safety.
        verdict = _try_code_security(intent.note)
        if verdict is not None:
            return verdict
        return _handle_llm(intent.note, history)
    return "I didn't understand that. Try `help`."


def _try_classifier_route(text: str) -> Optional[list[str]]:
    """Ask the TF intent classifier for a confident action route, if available.

    Returns a subcommand argv (e.g. ['security','status']) or None. Loading is
    lazy and any failure degrades to None so the chat never breaks.
    """
    try:
        from squad.chat import classifier as clf
        return clf.bridge.route(text)
    except Exception:
        return None


def _try_code_security(text: str) -> Optional[str]:
    """Vet a code snippet with the TF security classifier, if requested.

    Returns a formatted verdict string, or None when the message is not a
    code-safety request or the model is unavailable.
    """
    try:
        from squad.chat import classifier as clf
    except Exception:
        return None
    if not clf.looks_like_code_check(text):
        return None
    # Best-effort extraction: the code is whatever follows a ':' or ':' after
    # the prompt, or the trailing tokens otherwise.
    code = _extract_snippet(text)
    res = clf.security_verdict(code)
    if res is None:
        return "[chat] I can't vet that snippet right now (security model unavailable)."
    prob, verdict = res
    pct = prob * 100
    if verdict == "vulnerable":
        return (
            f"[chat] ⚠  security classifier: **VULNERABLE** (p={pct:.1f}%)\n\n"
            f"  snippet: {code}\n\n"
            "  Treat this as a finding. Run `squad security scan <target> repo C:/repo` "
            "for a full Nightwing assessment of the surrounding code."
        )
    return (
        f"[chat] ✓ security classifier: likely-safe (p={pct:.1f}%)\n\n"
        f"  snippet: {code}"
    )


def _extract_snippet(text: str) -> str:
    """Pull the code portion out of a code-safety request."""
    for sep in ("code:", "snippet:", "safe:"):
        if sep in text:
            after = text.split(sep, 1)[1].strip()
            if after:
                return after
    # No explicit separator: strip the leading prompt words and keep the rest.
    words = text.split()
    drop = 0
    for w in words:
        if w.lower() in ("check", "is", "this", "safe", "if", "for", "review",
                         "analyze", "audit", "the", "code", "snippet", "how",
                         "security", "vulnerabilities", "vulns", "?", ":"):
            drop += 1
        else:
            break
    return " ".join(words[drop:])


def _handle_interactive(intent: offline.Intent) -> str:
    """Turn a command that needs user input into a guided interaction."""
    note = intent.note or ""
    if not note:
        return "I can help you with that — what would you like to do?"
    # If the command has a natural next step, offer it and ask for confirmation.
    cmd = intent.cmd
    if cmd:
        pretty = " ".join(shlex.quote(c) for c in cmd)
        if _confirm(f"[chat] This needs your go-ahead. Run `squad {pretty}` now? [y/N] "):
            print(f"\n[chat] running: python -m squad {pretty}\n")
            return offline.run_command(cmd)
        return "Okay — I won't run it. You can run it yourself with:\n\n  squad " + pretty
    return f"[chat] {note}"


def _handle_llm(prompt: str, history: list[dict] | None = None) -> str:
    print("[chat] consulting the LLM tier...")
    try:
        reply = llm_tier.answer(prompt, history=history)
    except (llm_tier.NoKey, llm_tier.NoModel) as exc:
        # Fall back to the offline knowledge base first so users with no LLM key
        # (and no TensorFlow) still get a real answer, then intel search.
        print(f"[chat] LLM unavailable: {exc}")
        print("[chat] falling back to offline intelligence search...\n")
        q = _fallback_query(prompt)
        out = offline.run_command(["intel", "search", q])
        return out + "\n\n[chat] Tip: set an LLM API key (e.g. OPENAI_API_KEY, " \
                     "ANTHROPIC_API_KEY) or run a free local server (ollama/lmstudio) " \
                     "to unlock full research answers. See `squad providers`."
    prefix = f"[llm/{reply.model}] " if reply.model else "[llm] "
    return prefix + reply.text


_STOPWORDS = {
    "what", "is", "are", "the", "a", "an", "do", "does", "how", "why", "of",
    "to", "me", "my", "in", "on", "for", "and", "or", "with", "i", "can",
    "you", "tell", "about", "explain", "give", "me",
}


def _fallback_query(prompt: str) -> str:
    """Reduce a free-form question to a few high-value search keywords."""
    words = [w for w in prompt.split() if w.lower() not in _STOPWORDS]
    # Drop trailing punctuation from the first kept token.
    kept = [w.rstrip(",.;:!?") for w in words]
    return " ".join(kept[:6]) or prompt


def chat_loop(
    one_shot: Optional[str] = None,
    stream: Callable[[str], None] = None,
) -> int:
    """Run the REPL. If *one_shot* is given, handle a single message and exit.

    *stream* lets embedders capture printed output (defaults to ``print``).
    """
    import os

    os.environ.setdefault("TERM", "dumb")  # keep rich/tui quiet in non-tty use
    printer = stream or print

    if one_shot:
        reply = _handle(offline.parse(one_shot))
        if reply:
            printer(reply)
        return 0

    printer("Windows Dev Squad chat. Type `help` for commands, `exit` to quit.\n")
    while True:
        try:
            user = input("squad> ").strip()
        except (EOFError, KeyboardInterrupt):
            printer("\nbye.")
            return 0
        if not user:
            continue
        reply = _handle(offline.parse(user))
        if offline.parse(user).kind == "quit":
            printer(reply or "bye.")
            return 0
        if reply:
            printer(reply + "\n")