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
