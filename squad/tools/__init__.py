"""Typed tools for the squad agents."""

from __future__ import annotations

from squad.tools.basic import git_diff, git_status, read_file
from squad.tools.registry import TOOLS, get_tool, tier_of
from squad.tools.spec import ToolSpec

__all__ = ["ToolSpec", "TOOLS", "get_tool", "tier_of", "git_status", "git_diff", "read_file"]
