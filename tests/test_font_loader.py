from pathlib import Path

import pytest

from plotter_processor.font_loader import load_font


def test_loads_metrics_cmap_and_advance(test_font: Path) -> None:
    with load_font(test_font) as font:
        assert font.metrics.units_per_em == 1000
        assert font.metrics.ascent == 800
        assert font.advance_for_glyph(font.glyph_name_for_char("П")) == 600


def test_reports_missing_unicode_and_invalid_font(tmp_path: Path, test_font: Path) -> None:
    with load_font(test_font) as font, pytest.raises(ValueError, match=r"U\+2603"):
        font.validate_text("☃")
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    with pytest.raises(ValueError, match="Cannot open TTF"):
        load_font(broken)
