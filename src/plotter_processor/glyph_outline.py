from __future__ import annotations

from dataclasses import dataclass

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import PositionedGlyph


@dataclass(frozen=True, slots=True)
class ExactGlyphPath:
    char: str
    glyph_name: str
    glyph_index: int
    path_data: str


def extract_exact_outline(font: LoadedFont, positioned: PositionedGlyph) -> ExactGlyphPath | None:
    glyph = font.glyph_set[positioned.glyph_name]
    svg_pen = SVGPathPen(font.glyph_set)
    transform = (
        positioned.scale_mm_per_font_unit,
        0,
        0,
        -positioned.scale_mm_per_font_unit,
        positioned.x_mm,
        positioned.baseline_y_mm,
    )
    glyph.draw(TransformPen(svg_pen, transform))
    path_data = svg_pen.getCommands()
    if not path_data:
        return None
    return ExactGlyphPath(
        char=positioned.char,
        glyph_name=positioned.glyph_name,
        glyph_index=positioned.glyph_index,
        path_data=path_data,
    )


def extract_exact_outlines(
    font: LoadedFont, glyphs: list[PositionedGlyph]
) -> list[ExactGlyphPath]:
    return [outline for glyph in glyphs if (outline := extract_exact_outline(font, glyph))]
