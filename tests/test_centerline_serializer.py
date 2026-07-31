from pathlib import Path

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
)
from plotter_processor.centerline_font.serializer import (
    load_centerline_font,
    write_centerline_font_atomic,
)
from plotter_processor.models import Point


def test_centerline_cache_round_trip(tmp_path: Path) -> None:
    stroke = CenterlineStroke(0, (Point(0, 0), Point(10, 10)), False)
    glyph = CenterlineGlyph("A", 65, "A", 600, (stroke,))
    font = CompiledCenterlineFont(Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"A": glyph})
    target = tmp_path / "cache.json"
    write_centerline_font_atomic(font, target, config={"algorithm_version": 1})
    loaded, config = load_centerline_font(target)
    assert loaded.glyphs["A"].strokes == (stroke,)
    assert config == {"algorithm_version": 1}
