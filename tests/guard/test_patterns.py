"""Tests for destructive-pattern detection."""

from squad.guard import has_destructive


def test_detect_rm_rf():
    assert has_destructive("rm -rf /") is True


def test_detect_del_tree_windows():
    assert has_destructive("del /s /q C:\\") is True


def test_detect_remove_item_force():
    assert has_destructive("Remove-Item -Recurse -Force C:\\") is True


def test_detect_force_push():
    assert has_destructive("git push --force origin main") is True


def test_detect_fork_bomb():
    assert has_destructive(":(){ :|:& };:") is True


def test_detect_format_volume():
    assert has_destructive("Format-Volume -DriveLetter C") is True


def test_detect_shutdown():
    assert has_destructive("shutdown /s /t 0") is True


def test_benign_echo():
    assert has_destructive("echo hello") is False


def test_benign_python_call():
    assert has_destructive("add(2, 3)") is False


def test_empty_string():
    assert has_destructive("") is False


def test_case_insensitive():
    assert has_destructive("RM -RF /") is True
