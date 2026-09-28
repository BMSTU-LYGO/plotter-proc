from pathlib import Path

from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke, CompiledCenterlineFont, CompiledGlyphAnchor
from plotter_processor.fast_font import FastFont
from plotter_processor.fast_word import WordBuilder
from plotter_processor.models import Point


def _glyph(char: str, advance: int = 10, dot: bool = False) -> CenterlineGlyph:
    main = CenterlineStroke(0, (Point(0, 0), Point(8, 0)), False)
    strokes = (main, CenterlineStroke(1, (Point(4, 4), Point(4, 5)), False)) if dot else (main,)
    return CenterlineGlyph(char, ord(char), char, advance, strokes, entry_anchor=CompiledGlyphAnchor(Point(0, 0), 0, 0))


def _font() -> FastFont:
    return FastFont(CompiledCenterlineFont(Path("font.ttf"), "a" * 64, 1000, 800, -200, 0, {"а": _glyph("а"), "б": _glyph("б", dot=True)}), None)


def test_builds_continuous_primary_and_secondary_strokes() -> None:
    word = WordBuilder(_font()).build("аб")
    assert word.advance_font_units == 20
    assert len(word.primary) == 1
    assert word.primary[0].points[0] == Point(0, 0)
    assert word.primary[0].points[-1] == Point(18, 0)
    assert len(word.secondary) == 1
    assert word.secondary[0].points[0] == Point(14, 4)


def test_word_lru_is_bounded_and_returns_cached_geometry() -> None:
    builder = WordBuilder(_font(), cache_size=1)
    first = builder.build("а")
    assert builder.build("а") is first
    builder.build("б")
    assert builder.build("а") is not first
