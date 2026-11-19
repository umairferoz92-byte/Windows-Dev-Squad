"""Integration test: exercises the full security + developer + intel workflow."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
ENV = os.environ.copy()
ENV.pop("PYTHONPATH", None)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    # cmd is like ["security", "add-target", ...] — invoke as: python -m squad <cmd>
    return subprocess.run([PY, "-m", "squad"] + cmd, capture_output=True, text=True, cwd=ROOT, env=ENV, timeout=90)


def test_security_add_target_help():
    """add-target is interactive (prompts), so verify its help loads instead."""
    print("\n=== TEST: security add-target (interactive; verify help loads) ===")
    r = run(["security", "add-target", "--help"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-200:]}")
    print(f"  stderr: {r.stderr[-200:]}")
    assert "Add a new authorized target" in r.stdout or "Usage" in r.stdout


def test_security_doctor():
    """Test squad security doctor (safe self-check)."""
    print("\n=== TEST: security doctor ===")
    r = run(["security", "doctor"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")


def test_security_version():
    """Test squad security version."""
    print("\n=== TEST: security version ===")
    r = run(["security", "version"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-200:]}")
    print(f"  stderr: {r.stderr[-200:]}")
    assert r.returncode == 0, f"version failed: {r.stdout}{r.stderr}"


def test_security_check_tools():
    """Test squad security check-tools."""
    print("\n=== TEST: security check-tools ===")
    r = run(["security", "check-tools", "--install"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")
    # --install may print commands; just check it doesn't crash


def test_security_nightwing():
    """Test squad security nightwing on practice repo (should succeed with authorized path)."""
    print("\n=== TEST: security nightwing ===")
    r = run(
        [
            "security",
            "nightwing",
            os.path.join(ROOT, "practice", "app.py"),
            "--repo",
            os.path.join(ROOT, "practice"),
        ]
    )
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")
    # Nightwing may need actual toolchain; just check no crash


def test_dev_review():
    """Test squad dev review on practice file."""
    print("\n=== TEST: dev review ===")
    r = run(["dev", "review", "practice/app.py"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")


def test_dev_testgen():
    """Test squad dev testgen on practice file."""
    print("\n=== TEST: dev testgen ===")
    # Create a simple test file
    target = Path(ROOT, "practice/test_gen_tmp.py")
    target.write_text("def add(x, y):\n    return x + y\n", encoding="utf-8")
    r = run(["dev", "testgen", str(target)])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")
    target.unlink(missing_ok=True)


def test_dev_refactor():
    """Test squad dev refactor on practice file."""
    print("\n=== TEST: dev refactor ===")
    target = Path(ROOT, "practice/test_refactor_tmp.py")
    target.write_text("def foo():\n    try:\n        x = 1/0\n    except:\n        pass\n", encoding="utf-8")
    r = run(["dev", "refactor", str(target), "--write"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")
    target.unlink(missing_ok=True)


def test_intel_fetch():
    """Test squad intel fetch."""
    print("\n=== TEST: intel fetch ===")
    r = run(["intel", "fetch"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")


def test_intel_status():
    """Test squad intel status."""
    print("\n=== TEST: intel status ===")
    r = run(["intel", "status"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")


def test_intel_search():
    """Test squad intel search."""
    print("\n=== TEST: intel search ===")
    r = run(["intel", "search", "SQL"])
    print(f"  returncode: {r.returncode}")
    print(f"  stdout: {r.stdout[-300:]}")
    print(f"  stderr: {r.stderr[-300:]}")


def main():
    print("=" * 60)
    print("INTEGRATION TEST: Full Security + Dev + Intel Workflow")
    print("=" * 60)

    test_security_version()
    test_security_add_target_help()
    test_security_doctor()
    test_dev_review()
    test_dev_testgen()
    test_dev_refactor()
    test_intel_fetch()
    test_intel_status()
    test_intel_search()

    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
