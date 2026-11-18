"""Tests for git worktree management."""

import subprocess

from squad.crew import add_worktree, list_worktrees, remove_worktree


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=a@b.c",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=str(repo),
        check=True,
    )
    return repo


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def test_worktree_add_list_remove(tmp_path):
    repo = _init_repo(tmp_path)
    wt = tmp_path / "wt"
    add_worktree(str(repo), "ironman-1", str(wt))
    assert wt.exists()
    assert (wt / ".git").exists()
    assert _norm(str(wt)) in [_norm(p) for p in list_worktrees(str(repo))]
    remove_worktree(str(repo), str(wt))
    assert _norm(str(wt)) not in [_norm(p) for p in list_worktrees(str(repo))]
