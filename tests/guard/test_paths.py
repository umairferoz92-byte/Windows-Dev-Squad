"""Adversarial path-safety tests for the guard.

Covers path traversal, junctions, symlinks, short 8.3 names, encoded payloads,
chaining, Windows bypasses (case-insensitivity, trailing dots/spaces, alternate
data streams, ``\\\\?\\`` prefixes, UNC paths), and write-scope violations.
"""

import os

import pytest

from squad.guard import Policy, canonical, is_blocked, is_within

# --- canonicalization -------------------------------------------------------


def test_canonical_makes_relative_absolute():
    assert os.path.isabs(canonical("foo"))


def test_canonical_rejects_null_byte():
    with pytest.raises(ValueError):
        canonical("/repo/src/a\x00b")


# --- basic containment ------------------------------------------------------


def test_is_within_simple_file():
    assert is_within("/repo/src/main.py", ["/repo/src"]) is True


def test_is_within_exact_root():
    assert is_within("/repo/src", ["/repo/src"]) is True


def test_is_within_parent_traversal():
    assert is_within("/repo/src/../secret.txt", ["/repo/src"]) is False


def test_is_within_deep_traversal():
    assert is_within("/repo/src/a/../../b/../../etc/passwd", ["/repo/src"]) is False


def test_is_within_absolute_outside():
    assert is_within("/etc/passwd", ["/repo/src"]) is False


def test_is_within_sibling_prefix_not_confused():
    assert is_within("/repo/srctoo/file.py", ["/repo/src"]) is False


def test_is_within_chained_traversal():
    assert is_within("/repo/src/../src2/../../secret", ["/repo/src"]) is False


def test_is_within_new_nonexistent_file():
    assert is_within("/repo/src/new/deep/file.py", ["/repo/src"]) is True


def test_is_within_multiple_roots():
    assert is_within("/repo/tests/test_x.py", ["/repo/src", "/repo/tests"]) is True


def test_is_within_case_sensitivity():
    result = is_within("/repo/SRC/File.py", ["/repo/src"])
    if os.name == "nt":
        assert result is True
    else:
        assert result is False


# --- encoded payloads -------------------------------------------------------


def test_is_within_encoded_dotdot():
    assert is_within("/repo/src/%2e%2e/secret", ["/repo/src"]) is False


def test_is_within_double_encoded_dotdot():
    assert is_within("/repo/src/%252e%252e/secret", ["/repo/src"]) is False


def test_is_within_encoded_slash():
    assert is_within("/repo/src/%2e%2e%2fsecret", ["/repo/src"]) is False


def test_is_within_encoded_backslash():
    result = is_within("/repo/src/..%5c..%5csecret", ["/repo/src"])
    if os.name == "nt":
        assert result is False
    else:
        assert result is True


def test_is_within_encoded_git_component():
    p = Policy({"blocked_components": [".git"]})
    assert is_blocked("/repo/src/%2e%67%69%74/config", p) is True


# --- symlinks and junctions -------------------------------------------------


def test_is_within_symlink_escape(tmp_path):
    scope = tmp_path / "scope"
    outside = tmp_path / "outside"
    scope.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    link = scope / "link"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform/volume")
    assert is_within(str(link / "secret.txt"), [str(scope)]) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions only")
def test_is_within_junction_escape(tmp_path):
    scope = tmp_path / "scope"
    outside = tmp_path / "outside"
    scope.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    junction = scope / "junc"
    try:
        os.symlink(str(outside), str(junction), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("junctions unavailable (need developer mode or admin)")
    assert is_within(str(junction / "secret.txt"), [str(scope)]) is False


@pytest.mark.skipif(os.name != "nt", reason="8.3 short names are Windows-only")
def test_is_within_short_name_resolves(tmp_path):
    import ctypes

    scope = tmp_path / "scope"
    scope.mkdir()
    longdir = scope / "a-really-long-directory-name"
    longdir.mkdir()
    target = longdir / "secretfile.txt"
    target.write_text("x", encoding="utf-8")

    buf = ctypes.create_unicode_buffer(512)
    n = ctypes.windll.kernel32.GetShortPathNameW(str(target), buf, 512)
    if n == 0 or n >= 512:
        pytest.skip("8.3 short names unavailable on this volume")
    assert is_within(buf.value, [str(scope)]) is True


# --- Windows bypasses -------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Windows trailing-dot aliasing")
def test_is_within_trailing_dot_windows():
    assert canonical(r"C:\repo\file.txt.") == canonical(r"C:\repo\file.txt")


@pytest.mark.skipif(os.name != "nt", reason="Windows trailing-space aliasing")
def test_is_within_trailing_space_windows():
    assert canonical(r"C:\repo\file.txt ") == canonical(r"C:\repo\file.txt")


@pytest.mark.skipif(os.name != "nt", reason="Windows alternate data streams")
def test_is_within_ads_windows():
    assert canonical(r"C:\repo\file.txt:stream") == canonical(r"C:\repo\file.txt")


@pytest.mark.skipif(os.name != "nt", reason="Windows device-path prefix")
def test_is_within_device_prefix_windows():
    assert is_within(r"\\?\C:\repo\..\secret.txt", [r"C:\repo"]) is False


@pytest.mark.skipif(os.name != "nt", reason="UNC path handling")
def test_is_within_unc_not_within():
    assert is_within(r"\\server\share\file.txt", [r"C:\repo"]) is False


# --- blocked-path matching --------------------------------------------------


def test_is_blocked_dot_git():
    p = Policy({"write_scope": ["/repo/src"], "blocked_components": [".git"]})
    assert is_blocked("/repo/src/.git/config", p) is True


def test_is_blocked_dot_ssh():
    p = Policy({"blocked_components": [".ssh", ".aws"]})
    assert is_blocked("/home/u/.ssh/id_rsa", p) is True


def test_is_blocked_absolute_root(tmp_path):
    blocked_root = tmp_path / "blocked"
    blocked_root.mkdir()
    p = Policy({"blocked_paths": [str(blocked_root)]})
    assert is_blocked(str(blocked_root / "audit.log"), p) is True


def test_is_blocked_false_for_plain_path():
    p = Policy({"blocked_components": [".git"], "blocked_paths": []})
    assert is_blocked("/repo/src/main.py", p) is False


def test_is_blocked_case_insensitive_git():
    p = Policy({"blocked_components": [".git"]})
    if os.name == "nt":
        assert is_blocked("/repo/src/.GIT/config", p) is True
    else:
        assert is_blocked("/repo/src/.GIT/config", p) is False
