from __future__ import annotations

from plotter_processor.centerline_font.models import CompiledCenterlineFont
from plotter_processor.models import PageSpec, PathDocument, PlotterStroke, Point, PositionedGlyph


def build_centerline_paths(
    compiled_font: CompiledCenterlineFont,
    glyphs: list[PositionedGlyph],
    page: PageSpec,
) -> PathDocument:
    strokes: list[PlotterStroke] = []
    for positioned in glyphs:
        try:
            glyph = compiled_font.glyphs[positioned.char]
        except KeyError as error:
            raise ValueError(
                f'Centerline cache is missing glyph "{positioned.char}" '
                f"(U+{positioned.codepoint:04X})"
            ) from error
        for centerline in glyph.strokes:
            points = _dedupe(
                [
                    Point(
                        positioned.x_mm + point.x * positioned.scale_mm_per_font_unit,
                        positioned.baseline_y_mm
                        - point.y * positioned.scale_mm_per_font_unit,
                    )
                    for point in centerline.points
                ]
            )
            if len(points) < (3 if centerline.closed else 2):
                continue
            strokes.append(
                PlotterStroke(
                    id=len(strokes),
                    points=points,
                    closed=centerline.closed,
                    glyph_index=positioned.glyph_index,
                    char=positioned.char,
                    contour_index=centerline.id,
                    source_glyph_indices=(positioned.glyph_index,),
                    source_chars=positioned.char,
                    segment_types=("glyph",),
                    word_index=positioned.word_index,
                )
            )
    if not strokes:
        raise ValueError("Font processing produced no drawable paths")
    return PathDocument(
        page.width_mm,
        page.height_mm,
        strokes,
        list(compiled_font.warnings),
        {
            "coordinate_system": "page-mm-top-left",
            "pipeline": "ttf-centerline",
            "centerline_format": "plotter-centerline-font",
            "centerline_version": 2,
            "routing_strategy": "one_stroke_per_component",
            "font_sha256": compiled_font.font_sha256,
        },
    )


def _dedupe(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result
