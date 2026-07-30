from pathlib import Path

from plotter_processor.font_loader import load_font
from plotter_processor.glyph_outline import extract_exact_outline
from plotter_processor.models import PositionedGlyph


def test_extracts_transformed_quadratic_outline(test_font: Path) -> None:
    with load_font(test_font) as font:
        outline = extract_exact_outline(
            font,
            PositionedGlyph("П", 0x41F, font.glyph_name_for_char("П"), 10, 20, 3, 0.005, 0, 0),
        )
    assert outline is not None
    assert "Q" in outline.path_data
    assert "15.75" in outline.path_data
