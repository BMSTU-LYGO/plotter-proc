from pathlib import Path

import pytest

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


def test_dense_layout_keeps_strokes_inside_all_page_margins() -> None:
    config = FastLayoutConfig(page_width_mm=12, page_height_mm=12, font_size_mm=4)
    result = FastLayout(config).layout("аа аа аа аа аа аа", _builder())
    for page in result.pages:
        for stroke in page.strokes:
            for point in stroke.points:
                assert config.margin_left_mm <= point.x <= page.page_width_mm - config.margin_right_mm
                assert config.margin_top_mm <= point.y <= page.page_height_mm - config.margin_bottom_mm


def test_dense_defaults_use_two_mm_margins_and_automatic_spacing() -> None:
    config = FastLayoutConfig()
    assert (config.margin_left_mm, config.margin_right_mm, config.margin_top_mm, config.margin_bottom_mm) == (2, 2, 2, 2)
    assert config.resolved_line_height_mm == pytest.approx(4.4)
    assert config.resolved_word_spacing_mm == pytest.approx(0.8)
    assert config.line_gap_mm == pytest.approx(0.5)
    assert config.content_width_mm == pytest.approx(144)
    assert config.content_height_mm == pytest.approx(206)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"page_width_mm": 0},
        {"margin_left_mm": 0},
        {"word_spacing_mm": 0},
        {"line_height_mm": -1},
        {"line_gap_mm": -0.1},
        {"page_width_mm": 4, "margin_left_mm": 2, "margin_right_mm": 2},
    ),
)
def test_fast_layout_config_rejects_invalid_page_or_spacing(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        FastLayoutConfig(**kwargs)


def test_line_boxes_have_half_mm_vertical_gap() -> None:
    config = FastLayoutConfig(
        page_width_mm=30,
        page_height_mm=30,
        margin_left_mm=2,
        margin_right_mm=2,
        margin_top_mm=2,
        margin_bottom_mm=2,
        font_size_mm=4,
        line_gap_mm=0.5,
    )
    result = FastLayout(config).layout("а\nа", _builder())
    first, second = result.pages[0].strokes
    first_box_bottom = max(point.y for point in first.points)
    second_box_top = min(point.y for point in second.points)
    # The synthetic glyph occupies only part of the font line box, so its
    # visible gap cannot be smaller than the configured line-box gap.
    assert second_box_top - first_box_bottom >= 0.5 - 1e-9
