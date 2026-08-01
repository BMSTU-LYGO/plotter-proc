from pathlib import Path

import pytest

from plotter_processor.font_loader import load_font
from plotter_processor.text_shaper import shape_text_run


def test_harfbuzz_reports_clear_missing_dependency_or_shapes() -> None:
    with load_font(Path("assets/1.ttf")) as font:
        try:
            run = shape_text_run("обычный", font)
        except RuntimeError as error:
            assert "uharfbuzz" in str(error)
        else:
            assert run.glyphs
            assert all(glyph.font.sha256 for glyph in run.glyphs)


def test_invalid_layout_dependency_does_not_silently_fallback(monkeypatch) -> None:
    import builtins

    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "uharfbuzz":
            raise ImportError
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with load_font(Path("assets/1.ttf")) as font, pytest.raises(RuntimeError, match="legacy"):
        shape_text_run("тест", font)
