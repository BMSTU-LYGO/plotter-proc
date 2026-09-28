from pathlib import Path

from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke, CompiledPlotterFont
from plotter_processor.fast_font import FastFont
from plotter_processor.fast_layout import FastLayout, FastLayoutConfig
from plotter_processor.fast_word import WordBuilder
from plotter_processor.models import Point


def _builder() -> WordBuilder:
    glyph = CenterlineGlyph("а", ord("а"), "a", 500, (CenterlineStroke(0, (Point(0, 0), Point(400, 500)), False),))
    compiled = CompiledPlotterFont(Path("font.ttf"), "hash", 1000, 800, -200, 0, {"а": glyph})
    return WordBuilder(FastFont(compiled, None), cache_size=4)


def test_fast_layout_wraps_and_paginates_linearly() -> None:
    config = FastLayoutConfig(20, 13, 1, 1, 1, 1, 4, 5, 1)
    result = FastLayout(config).layout("аа аа\n\nаа аа аа", _builder())
    assert result.words_total == 5
    assert len(result.pages) >= 2
    assert result.pen_down_count >= result.words_total


def test_fast_layout_reuses_repeated_word() -> None:
    result = FastLayout(FastLayoutConfig()).layout("аа аа аа", _builder())
    assert result.cache_misses == 1
    assert result.cache_hits == 2
