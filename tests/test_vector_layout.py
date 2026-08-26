from pathlib import Path

import pytest

from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec
from plotter_processor.vector_layout import layout_text


def test_layout_wraps_and_uses_millimeters(test_font: Path) -> None:
    with load_font(test_font) as font:
        result = layout_text(
            ["Привет мир привет"],
            font,
            PageSpec("tiny", 35, 50),
            {"left": 5, "right": 5, "top": 5, "bottom": 5},
            {"em_size_mm": 5, "line_height_multiplier": 1.25, "paragraph_spacing_mm": 2},
        )
    assert result.line_count > 1
    assert all(glyph.scale_mm_per_font_unit == 0.005 for glyph in result.glyphs)


def test_layout_detects_overflow(test_font: Path) -> None:
    with load_font(test_font) as font, pytest.raises(ValueError, match="does not fit"):
        layout_text(
            ["Привет " * 50],
            font,
            PageSpec("tiny", 25, 15),
            {"left": 2, "right": 2, "top": 2, "bottom": 2},
            {"em_size_mm": 6, "line_height_multiplier": 1.3, "paragraph_spacing_mm": 2},
        )


def test_layout_clamps_accidental_multi_space_word_gap(test_font: Path) -> None:
    options = {
        "em_size_mm": 5,
        "line_height_multiplier": 1.25,
        "paragraph_spacing_mm": 2,
        "max_word_space_factor": 1.5,
    }
    with load_font(test_font) as font:
        normal = layout_text(
            ["а б"], font, PageSpec("wide", 100, 50),
            {"left": 5, "right": 5, "top": 5, "bottom": 5}, options,
        )
        noisy = layout_text(
            ["а          б"], font, PageSpec("wide", 100, 50),
            {"left": 5, "right": 5, "top": 5, "bottom": 5}, options,
        )

    normal_gap = normal.glyphs[1].x_mm - (
        normal.glyphs[0].x_mm + normal.glyphs[0].advance_mm
    )
    noisy_gap = noisy.glyphs[1].x_mm - (
        noisy.glyphs[0].x_mm + noisy.glyphs[0].advance_mm
    )
    assert noisy_gap <= normal_gap * 1.5 + 1e-9

    with load_font(test_font) as font:
        tabbed = layout_text(
            ["а\tб"], font, PageSpec("wide", 100, 50),
            {"left": 5, "right": 5, "top": 5, "bottom": 5}, options,
        )
    tab_gap = tabbed.glyphs[1].x_mm - (
        tabbed.glyphs[0].x_mm + tabbed.glyphs[0].advance_mm
    )
    assert tab_gap > noisy_gap
