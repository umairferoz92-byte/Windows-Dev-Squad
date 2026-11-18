"""Classify changed files into the flag categories the report must call out."""

from __future__ import annotations

_CATEGORIES = [
    ("test_files", ("tests/", "test_", "_test.py", "conftest.py")),
    (
        "dependencies",
        (
            "requirements",
            "Pipfile",
            "poetry.lock",
            "package.json",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
        ),
    ),
    (
        "lockfiles",
        (
            "-lock.txt",
            "poetry.lock",
            "package-lock.json",
            "yarn.lock",
            "uv.lock",
            "requirements-lock",
        ),
    ),
    ("ci", (".github/workflows", "azure-pipelines", ".gitlab-ci.yml", "Jenkinsfile", ".circleci")),
    ("git_hooks", (".git/hooks", "pre-commit", ".pre-commit-config.yaml", "commit-msg")),
    ("config", ("squad.yaml", "guard.yaml", "prices.yaml", ".env", "scope")),
    ("build", ("Makefile", "Dockerfile", "CMakeLists.txt", "setup.py")),
    (
        "lint_type_test_coverage",
        ("ruff.toml", ".ruff.toml", "mypy.ini", ".coveragerc", "pytest.ini", "tox.ini"),
    ),
]


def classify_file(path: str) -> set[str]:
    norm = path.replace("\\", "/")
    matched: set[str] = set()
    for category, needles in _CATEGORIES:
        if any(n in norm for n in needles):
            matched.add(category)
    return matched


def classify_changed_files(paths: list[str]) -> list[dict]:
    return [{"path": p, "categories": sorted(classify_file(p))} for p in paths]


def flagged_files(paths: list[str]) -> list[dict]:
    """Return only the changed files that need flagging."""
    return [entry for entry in classify_changed_files(paths) if entry["categories"]]
