"""TensorFlow intent/security bridge for the chatbot.

When the rule-based parser (squad.chat.offline) misses a request or only has a
weak hit, we consult the locally-trained TensorFlow intent classifier to
disambiguate and route to the correct ``squad`` action. The security classifier
is also exposed here so the agent can flag vulnerable code snippets.

Both models are loaded lazily and every call is optional: if TensorFlow or the
artifacts are missing, these helpers degrade to ``None`` / the raw text so the
chatbot keeps working in fully-offline installs.
"""

from __future__ import annotations

import re


def _load(which: str):
    """Lazily import + instantiate a model; return None on any failure."""
    try:
        from pathlib import Path

        from squad.models import infer
        from squad.models.train import ARTIFACTS

        d = Path(ARTIFACTS) / which
        if not (d / "model.keras").exists():
            return None
        return infer.IntentClassifier(d) if which == "intent" else infer.SecurityClassifier(d)
    except Exception:
        return None


# intent-classifier label -> squad subcommand template.
# ``{arg}`` is filled from the user's message; None => no arg needed.
_LABEL_CMD: dict[str, list[str] | None] = {
    "review": ["dev", "review", "{arg}"],
    "testgen": ["dev", "testgen", "{arg}"],
    "refactor": ["dev", "refactor", "{arg}"],
    "scan": ["security", "nightwing", "{arg}", "--phases", "ab"],
    "fetch": ["intel", "fetch"],
    "search": ["intel", "search", "{arg}"],
    "status": ["security", "status"],
    "doctor": ["security", "doctor"],
    "tools": ["security", "check-tools"],
    "export": ["security", "export", "{arg}", "--format", "csv"],
}

_NEEDS_ARG = {"review", "testgen", "refactor", "scan", "search", "export"}

# Rough extraction: first bare token that looks like a path/url/query arg.
_ARG_RE = re.compile(r"([\w.\\/:@_-]+)(?:\s+repo\s+([\w.\\/:@_-]+))?", re.IGNORECASE)
# A token counts as a real target only if it looks like a path, URL, IP, or CVE.
_PATHY = re.compile(
    r"(?:[A-Za-z]:[\\/]|\./|\.\./|/|://|\.\w+$|\.py$|\.js$|\.go$|\.rs$|\.java$|"
    r"(?:\d{1,3}\.){3}\d{1,3}|CVE-\d|CWE-\d)",
    re.IGNORECASE,
)


def _extract_arg(text: str, label: str) -> str | None:
    if label not in _NEEDS_ARG:
        return None
    # Scan every bare token; return the first one that looks like a real target.
    for m in _ARG_RE.finditer(text):
        for grp in (m.group(2), m.group(1)):
            if grp:
                cand = grp.strip()
                if _PATHY.search(cand):
                    return cand
    return None


class ClassifierBridge:
    """Loads the TF models once and routes free text to squad actions."""

    def __init__(self):
        self._intent = None
        self._security = None
        self._loaded = False

    def _ensure(self):
        if not self._loaded:
            try:
                self._intent = _load("intent")
                self._security = _load("security")
            except Exception:
                self._intent = None
                self._security = None
            self._loaded = True

    @property
    def available(self) -> bool:
        self._ensure()
        return self._intent is not None

    def intent(self, text: str):
        """Return (label, confidence) or (None, 0.0) when unavailable."""
        self._ensure()
        if self._intent is None:
            return None, 0.0
        try:
            return self._intent.predict(text)
        except Exception:
            return None, 0.0

    def security(self, code: str) -> tuple[float, str] | None:
        """Return (probability, verdict) for a code snippet, or None."""
        self._ensure()
        if self._security is None:
            return None
        try:
            return self._security.predict(code)  # type: ignore[return-value]
        except Exception:
            return None

    def route(self, text: str):
        """Return a full ``squad`` subcommand list, or None if not confident."""
        label, conf = self.intent(text)
        if not label or conf < 0.5 or label not in _LABEL_CMD:
            return None
        arg = _extract_arg(text, label)
        if label in _NEEDS_ARG and not arg:
            return None
        template = _LABEL_CMD[label]
        return [t.format(arg=arg) if t == "{arg}" else t for t in template] if template else None


# A module-level singleton for the chat REPL to reuse.
bridge = ClassifierBridge()


# Phrases that mean "review this code for security issues".
_SECURITY_ASK = re.compile(
    r"\b(check|review|analyze|audit|inspect|scan|is\s+this|how\s+safe|safe\??)\b"
    r".{0,40}(safe|secure|vulnerab|exploit|hack|inject|risky|danger)",
    re.IGNORECASE,
)


def looks_like_code_check(text: str) -> bool:
    """True when the user is asking to vet a code snippet for safety."""
    return bool(_SECURITY_ASK.search(text))


def security_verdict(code: str) -> tuple[float, str] | None:
    """Run the code-security classifier on a snippet.

    Returns (probability, verdict) where verdict is 'vulnerable' or
    'likely-safe', or None when the model/artifacts are unavailable.
    """
    if not code or not code.strip():
        return None
    return bridge.security(code)
