from pathlib import Path

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CenterlineStroke,
    CompiledCenterlineFont,
    CompiledPlotterFont,
    compiled_glyph_metadata,
)
from plotter_processor.centerline_font.serializer import (
    from_data,
    load_centerline_font,
    to_data,
    write_centerline_font_atomic,
)
from plotter_processor.models import Point


def test_centerline_cache_round_trip(tmp_path: Path) -> None:
    stroke = CenterlineStroke(0, (Point(0, 0), Point(10, 10)), False)
    entry, exit_anchor, metadata = compiled_glyph_metadata((stroke,))
    glyph = CenterlineGlyph(
        "A", 65, "A", 600, (stroke,), entry_anchor=entry,
        exit_anchor=exit_anchor, stroke_metadata=metadata,
    )
    font = CompiledCenterlineFont(Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"A": glyph})
    target = tmp_path / "cache.json"
    write_centerline_font_atomic(font, target, config={"algorithm_version": 1})
    loaded, config = load_centerline_font(target)
    assert isinstance(loaded, CompiledPlotterFont)
    assert loaded.glyphs["A"].strokes == (stroke,)
    assert loaded.glyphs["A"].entry_anchor == entry
    assert loaded.glyphs["A"].exit_anchor == exit_anchor
    assert loaded.glyphs["A"].stroke_metadata == metadata
    assert loaded.source_fingerprint == "a" * 64
    assert config == {"algorithm_version": 1}


def test_old_compiled_font_schema_is_rejected() -> None:
    font = CompiledCenterlineFont(
        Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {}
    )
    payload = to_data(font, config={})
    payload["version"] = 2

    try:
        from_data(payload)
    except ValueError as error:
        assert "Unsupported centerline font cache" in str(error)
    else:
        raise AssertionError("old compiled font schema must be rejected")
