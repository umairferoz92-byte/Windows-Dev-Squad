"""Git worktree management for the parallel squad (one worktree per agent)."""

from __future__ import annotations

import shutil
import subprocess


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git not found on PATH")
    proc = subprocess.run(
        [git, "-C", repo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def add_worktree(repo: str, branch: str, path: str, base: str = "HEAD") -> None:
    """Create a new branch and a worktree for it."""
    _git(repo, "worktree", "add", "-b", branch, str(path), base)


def list_worktrees(repo: str) -> list[str]:
    proc = _git(repo, "worktree", "list", "--porcelain")
    paths = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree ") :])
    return paths


def remove_worktree(repo: str, path: str) -> None:
    _git(repo, "worktree", "remove", "--force", str(path))
