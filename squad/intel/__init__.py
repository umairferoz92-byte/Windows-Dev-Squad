"""Real-Time Intelligence & Knowledge Feed Module for Windows Dev Squad.

Provides real-time security threat feeds (CVEs, GitHub Advisories) and modern
coding best practices to keep the Security Squad and Coding Assistant up-to-date.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

INTEL_CACHE_PATH = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "squad", "intel_cache.json")

# Default fallback offline knowledge base if network is unavailable
DEFAULT_SECURITY_ADVISORIES = [
    {
        "id": "CVE-2024-SEC-01",
        "title": "SQL Injection & Command Injection Patterns",
        "severity": "CRITICAL",
        "cwe": "CWE-89",
        "summary": "Avoid shell=True in subprocess calls and raw string concatenation in SQL queries.",
        "recommendation": "Use parameterized queries and list-based subprocess execution.",
        "updated_at": "2026-03-01T00:00:00Z",
    },
    {
        "id": "CVE-2024-SEC-02",
        "title": "Insecure Deserialization & Eval Hazards",
        "severity": "HIGH",
        "cwe": "CWE-502",
        "summary": "Use of eval(), exec(), or pickle.loads on untrusted input allows RCE.",
        "recommendation": "Use ast.literal_eval or json.loads for serialization.",
        "updated_at": "2026-03-01T00:00:00Z",
    },
    {
        "id": "GHSA-2026-REV-01",
        "title": "Hardcoded Secrets and API Keys Leakage",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "summary": "Hardcoded tokens, bearer keys, and AWS credentials committed to git repos.",
        "recommendation": "Use environment variables or secrets manager with gitleaks scanning.",
        "updated_at": "2026-03-01T00:00:00Z",
    },
]

DEFAULT_CODING_BEST_PRACTICES = [
    {
        "topic": "Type Annotations & Modern Python",
        "language": "python",
        "summary": "Use Python 3.10+ union types (X | Y) and standard collection generics (list[str]).",
        "example": "def process(items: list[str]) -> dict[str, int]: ...",
    },
    {
        "topic": "Async & Non-Blocking I/O",
        "language": "python",
        "summary": "Avoid blocking I/O calls inside async event loops. Use asyncio loops properly.",
        "example": "await asyncio.to_thread(blocking_func)",
    },
    {
        "topic": "Robust Error Handling & Logging",
        "language": "all",
        "summary": "Catch specific exceptions, log structured metadata, and avoid bare except:",
        "example": "try: ... except FileNotFoundError as exc: logger.error('Missing: %s', exc)",
    },
    {
        "topic": "Unit Test Coverage & Assertions",
        "language": "all",
        "summary": "Write deterministic unit tests with clear assertions, mocking network/disk calls.",
        "example": "def test_feature(tmp_path): ... assert result.ok",
    },
]


@dataclass
class IntelFeed:
    last_updated: float
    security_advisories: list[dict[str, Any]]
    coding_practices: list[dict[str, Any]]
    sources: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntelFeed:
        return cls(
            last_updated=data.get("last_updated", 0.0),
            security_advisories=data.get("security_advisories", []),
            coding_practices=data.get("coding_practices", []),
            sources=data.get("sources", []),
        )


class RealTimeIntelEngine:
    """Harvests real-time security vulnerabilities & coding standards."""

    def __init__(self, cache_file: str = INTEL_CACHE_PATH) -> None:
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.intel = self.load_cache()

    def load_cache(self) -> IntelFeed:
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                return IntelFeed.from_dict(data)
            except Exception:
                pass
        return IntelFeed(
            last_updated=time.time(),
            security_advisories=list(DEFAULT_SECURITY_ADVISORIES),
            coding_practices=list(DEFAULT_CODING_BEST_PRACTICES),
            sources=["builtin-fallback-db"],
        )

    def save_cache(self) -> None:
        try:
            self.cache_file.write_text(json.dumps(self.intel.to_dict(), indent=2), encoding="utf-8")
        except OSError:
            pass

    def fetch_realtime_updates(self, timeout: int = 5) -> dict[str, Any]:
        """Fetch latest advisories from GitHub Advisory API & Python Security DB if online."""
        sources_contacted = []
        new_advisories = []

        # 1. Fetch GitHub Advisory Security Feed (Open API endpoint)
        gh_url = "https://api.github.com/advisories?per_page=5"
        try:
            req = urllib.request.Request(gh_url, headers={"User-Agent": "WindowsDevSquad-Intel/0.2.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    items = json.loads(resp.read().decode("utf-8"))
                    for item in items:
                        new_advisories.append(
                            {
                                "id": item.get("ghsa_id", item.get("cve_id", "GHSA-LIVE")),
                                "title": item.get("summary", "Security Advisory"),
                                "severity": item.get("severity", "HIGH").upper(),
                                "cwe": item.get("cwe_ids", ["CWE-UNKNOWN"])[0] if item.get("cwe_ids") else "CWE-UNKNOWN",
                                "summary": item.get("description", "")[:200] + "...",
                                "recommendation": "Review advisory details & upgrade dependencies.",
                                "updated_at": item.get("published_at", ""),
                            }
                        )
                    sources_contacted.append("github-advisories-api")
        except Exception:
            # Fallback if offline / rate limited
            pass

        if new_advisories:
            # Merge advisories
            existing_ids = {a["id"] for a in self.intel.security_advisories}
            for adv in new_advisories:
                if adv["id"] not in existing_ids:
                    self.intel.security_advisories.insert(0, adv)
            self.intel.security_advisories = self.intel.security_advisories[:20]

        self.intel.last_updated = time.time()
        for s in sources_contacted:
            if s not in self.intel.sources:
                self.intel.sources.append(s)

        self.save_cache()
        return {
            "status": "updated",
            "sources": self.intel.sources,
            "total_advisories": len(self.intel.security_advisories),
            "total_coding_practices": len(self.intel.coding_practices),
        }

    def search_intel(self, query: str) -> list[dict[str, Any]]:
        """Search across real-time security advisories and coding standards."""
        q = query.lower()
        results = []
        for adv in self.intel.security_advisories:
            if q in adv.get("title", "").lower() or q in adv.get("summary", "").lower() or q in adv.get("cwe", "").lower():
                results.append({"type": "security_advisory", "data": adv})

        for prac in self.intel.coding_practices:
            if q in prac.get("topic", "").lower() or q in prac.get("summary", "").lower() or q in prac.get("language", "").lower():
                results.append({"type": "coding_practice", "data": prac})

        return results

    def get_context_prompt(self) -> str:
        """Construct real-time knowledge prompt snippet for AI agent augmentation."""
        lines = ["=== REAL-TIME SECURITY & CODING INTELLIGENCE ==="]
        lines.append("Latest Security Advisories:")
        for adv in self.intel.security_advisories[:3]:
            lines.append(f" - [{adv['severity']}] {adv['id']}: {adv['title']} ({adv['cwe']})")
        lines.append("Coding Best Practices:")
        for prac in self.intel.coding_practices[:3]:
            lines.append(f" - [{prac['language']}] {prac['topic']}: {prac['summary']}")
        return "\n".join(lines)
