from pathlib import Path


def test_update_6_visual_corpus_exists() -> None:
    root = Path("tests/visual/update_6")
    assert "ъ ь ы" in (root / "pacifico_problem_glyphs.txt").read_text(encoding="utf-8")
    assert "программирование" in (root / "pacifico_connections.txt").read_text(
        encoding="utf-8"
    )
    assert "∫ f(x) dx" in (root / "math_symbols.txt").read_text(encoding="utf-8")


def test_baseline_tool_declares_stable_schema() -> None:
    source = Path("tools/update_6_baseline.py").read_text(encoding="utf-8")
    assert '"schema_version": 1' in source
    assert '"font_sha256"' in source
    assert '"problem_glyphs"' in source
