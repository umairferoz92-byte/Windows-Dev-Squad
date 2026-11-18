"""Tests for crew assembly (names, size, roles, caps)."""

import pytest

from squad.crew import HARD_MAX_AGENTS, assemble_crew


def test_default_five_core_roles():
    crew = assemble_crew(5)
    assert [a.role for a in crew] == ["coordinator", "coder", "tester", "security", "quality"]


def test_size_is_capped():
    assert len(assemble_crew(50)) == HARD_MAX_AGENTS


def test_minimum_one_agent():
    crew = assemble_crew(0)
    assert len(crew) == 1
    assert crew[0].role == "coordinator"


def test_names_are_used():
    crew = assemble_crew(3, names=["a", "b", "c"])
    assert [a.name for a in crew] == ["a", "b", "c"]


def test_auto_names_are_unique():
    crew = assemble_crew(7)
    names = [a.name for a in crew]
    assert len(set(names)) == len(names)


def test_duplicate_names_rejected():
    with pytest.raises(ValueError):
        assemble_crew(3, names=["a", "a"])


def test_extra_agents_get_extra_roles():
    crew = assemble_crew(7)
    assert crew[5].role in ("docs", "performance", "dependencies", "integration", "evals")
    assert crew[6].role in ("docs", "performance", "dependencies", "integration", "evals")
