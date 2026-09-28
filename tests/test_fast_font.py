from pathlib import Path

from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke, CompiledCenterlineFont
from plotter_processor.centerline_font.serializer import write_centerline_font_atomic
from plotter_processor.fast_font import FastFont
from plotter_processor.models import Point


def test_loads_cache_once_and_uses_cached_fallback(tmp_path: Path) -> None:
    glyph = CenterlineGlyph("?", 63, "question", 10, (CenterlineStroke(0, (Point(0, 0), Point(5, 0)), False),))
    cache = tmp_path / "font.json"
    write_centerline_font_atomic(
        CompiledCenterlineFont(Path("font.ttf"), "f" * 64, 1000, 800, -200, 0, {"?": glyph}),
        cache,
        config={},
    )
    FastFont.clear_cache()
    first = FastFont.load(cache)
    second = FastFont.load(cache)
    assert first is second
    assert first.get("missing") is not None
    assert first.get("missing").char == "?"
