from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from plotter_processor.centerline_font.models import RasterGlyph
from plotter_processor.font_loader import LoadedFont, load_font


def render_glyph(
    font_path: str | Path,
    char: str,
    *,
    units_per_em: int,
    em_resolution_px: int,
    padding_px: int,
    loaded_font: LoadedFont | None = None,
) -> RasterGlyph:
    if len(char) != 1:
        raise ValueError("Expected exactly one character")
    owned = loaded_font is None
    font = loaded_font or load_font(font_path)
    try:
        if units_per_em != font.metrics.units_per_em:
            raise ValueError("units_per_em does not match TTF")
        glyph_name = font.glyph_name_for_char(char)
        advance = font.advance_for_glyph(glyph_name)
        scale = em_resolution_px / units_per_em
        pil_font = ImageFont.truetype(str(font_path), em_resolution_px)
        bbox = pil_font.getbbox(char, anchor="ls")
        baseline_x = padding_px + max(0, -bbox[0])
        baseline_y = padding_px + font.metrics.ascent * scale
        width = max(
            round(advance * scale + 2 * padding_px),
            round(baseline_x + bbox[2] + padding_px),
        )
        height = round(
            padding_px * 2 + (font.metrics.ascent - font.metrics.descent) * scale
        )
        image = Image.new("L", (max(width, 1), max(height, 1)), 255)
        ImageDraw.Draw(image).text(
            (baseline_x, baseline_y), char, font=pil_font, fill=0, anchor="ls"
        )
        grayscale = np.asarray(image, dtype=np.uint8).copy()
        return RasterGlyph(
            char=char,
            codepoint=ord(char),
            glyph_name=glyph_name,
            width=grayscale.shape[1],
            height=grayscale.shape[0],
            baseline_x_px=baseline_x,
            baseline_y_px=baseline_y,
            pixels_per_font_unit=scale,
            advance_font_units=advance,
            grayscale=grayscale,
        )
    finally:
        if owned:
            font.close()
