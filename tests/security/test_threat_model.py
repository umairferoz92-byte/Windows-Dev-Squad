"""Every threat in docs/THREATS.md must be covered by a test or an accepted risk."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _threats() -> list[str]:
    text = (ROOT / "docs" / "THREATS.md").read_text(encoding="utf-8")
    blocks = []
    current = None
    for line in text.splitlines():
        if line.startswith("### TH-"):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None and line.strip():
            current.append(line)
    if current is not None:
        blocks.append(current)
    return ["\n".join(b) for b in blocks]


def test_every_threat_is_covered():
    blocks = _threats()
    assert len(blocks) >= 10, f"expected at least 10 threats, found {len(blocks)}"
    for block in blocks:
        assert "Test:" in block or "Accepted risk:" in block, f"uncovered threat:\n{block}"


def test_referenced_test_files_exist():
    text = (ROOT / "docs" / "THREATS.md").read_text(encoding="utf-8")
    refs = {line.strip().removeprefix("Test: ").strip().strip("`") for line in text.splitlines() if line.strip().startswith("Test:")}
    for ref in refs:
        assert ref, "empty Test: reference in THREATS.md"
        assert (ROOT / ref).exists(), f"missing referenced test: {ref}"


def test_assets_and_attackers_present():
    text = (ROOT / "docs" / "THREATS.md").read_text(encoding="utf-8")
    assert "## Assets" in text and "## Attackers" in text
    assert "OWASP" in text
