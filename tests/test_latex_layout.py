from pathlib import Path

import pytest
import yaml

from plotter_processor.font_loader import load_font
from plotter_processor.latex_layout import layout_latex_paragraph
from plotter_processor.latex_renderer import MathTextRenderer


def _config() -> dict[str, object]:
    return yaml.safe_load(Path("configs/layout.yaml").read_text(encoding="utf-8"))


def test_inline_formula_shares_line_and_increases_height(test_font: Path) -> None:
    config = _config()
    with load_font(test_font) as font:
        plain, _ = layout_latex_paragraph(
            "before $x$ after", font, 120, config["sizes"]["normal"], config["latex"],
            MathTextRenderer(), formula_index_start=0, element_id="text",
        )
        tall, _ = layout_latex_paragraph(
            r"before $\frac{a}{b}$ after", font, 120,
            config["sizes"]["normal"], config["latex"], MathTextRenderer(),
            formula_index_start=0, element_id="text",
        )

    assert len(plain) == 1
    assert plain[0].glyphs and plain[0].formula_strokes
    assert tall[0].height_mm >= plain[0].height_mm


def test_inline_formula_wraps_whole_and_block_is_centered(test_font: Path) -> None:
    config = _config()
    with load_font(test_font) as font:
        inline, _ = layout_latex_paragraph(
            "many words before formula $x^2$", font, 42,
            config["sizes"]["normal"], config["latex"], MathTextRenderer(),
            formula_index_start=0, element_id="text",
        )
        block, _ = layout_latex_paragraph(
            r"$$\frac{a}{b}$$", font, 80, config["sizes"]["normal"],
            config["latex"], MathTextRenderer(), formula_index_start=0,
            element_id="text",
        )

    assert len(inline) >= 2
    formula_line = next(line for line in inline if line.formula_strokes)
    assert formula_line.formula_infos[0].expression == "x^2"
    points = [point for stroke in block[0].formula_strokes for point in stroke.points]
    bbox_center = (min(point.x for point in points) + max(point.x for point in points)) / 2
    assert bbox_center == pytest.approx(40.0, abs=0.2)
    assert block[0].spacing_before_mm == 2.0
    assert block[0].spacing_after_mm == 2.0
