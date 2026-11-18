"""Unit tests for Developer Assistant (squad.dev) and Real-Time Intel (squad.intel)."""

from __future__ import annotations

import os
import pytest
from squad.dev import DeveloperAssistant
from squad.intel import RealTimeIntelEngine


def test_intel_engine_builtin_fallback(tmp_path):
    cache_file = tmp_path / "test_intel_cache.json"
    engine = RealTimeIntelEngine(cache_file=str(cache_file))

    assert len(engine.intel.security_advisories) > 0
    assert len(engine.intel.coding_practices) > 0

    results = engine.search_intel("SQL")
    assert len(results) > 0
    assert results[0]["type"] == "security_advisory"

    results_prac = engine.search_intel("Python")
    assert len(results_prac) > 0

    prompt = engine.get_context_prompt()
    assert "REAL-TIME SECURITY & CODING INTELLIGENCE" in prompt


def test_intel_fetch_updates(tmp_path):
    cache_file = tmp_path / "test_intel_cache.json"
    engine = RealTimeIntelEngine(cache_file=str(cache_file))

    res = engine.fetch_realtime_updates(timeout=2)
    assert res["status"] == "updated"
    assert cache_file.exists()


def test_developer_assistant_review(tmp_path):
    sample_file = tmp_path / "sample_code.py"
    sample_file.write_text("""API_KEY = "1234567890"

def calculate(x, y):
    try:
        eval("x + y")
    except:
        pass
""", encoding="utf-8")

    assistant = DeveloperAssistant(cwd=str(tmp_path))
    res = assistant.review_code(str(sample_file))

    assert res.score < 100
    assert res.security_findings_count > 0
    assert "Developer Code Review" in res.report_markdown


def test_developer_assistant_testgen(tmp_path):
    sample_file = tmp_path / "helpers.py"
    sample_file.write_text("""def compute_total(price: float, tax: float) -> float:
    return price * (1 + tax)
""", encoding="utf-8")

    assistant = DeveloperAssistant(cwd=str(tmp_path))
    res = assistant.generate_tests(str(sample_file))

    assert res.tests_generated == 1
    assert os.path.exists(res.test_file_created)
    assert "def test_compute_total_basic():" in res.content


def test_developer_assistant_refactor(tmp_path):
    sample_file = tmp_path / "legacy.py"
    sample_file.write_text("""def do_something():
    try:
        x = 1
    except:
        pass
""", encoding="utf-8")

    assistant = DeveloperAssistant(cwd=str(tmp_path))
    refactored = assistant.refactor_code(str(sample_file))

    assert "from __future__ import annotations" in refactored
    assert "except Exception:" in refactored
