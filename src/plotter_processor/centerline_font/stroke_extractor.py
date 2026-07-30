from __future__ import annotations

import numpy as np

from plotter_processor.centerline_font.models import (
    CenterlineStroke,
    RasterGlyph,
    SkeletonEdge,
)
from plotter_processor.models import Point


def extract_raw_strokes(
    edges: list[SkeletonEdge],
    raster: RasterGlyph,
    distance: np.ndarray,
) -> list[CenterlineStroke]:
    strokes: list[CenterlineStroke] = []
    for edge in sorted(edges, key=lambda item: item.id):
        pixels = list(edge.pixels)
        if len(pixels) < 2:
            continue
        points = [_to_font_point(pixel, raster) for pixel in pixels]
        if not edge.closed and _point_key(points[-1]) < _point_key(points[0]):
            points.reverse()
        strokes.append(CenterlineStroke(len(strokes), tuple(points), edge.closed))
    return strokes


def _to_font_point(pixel: tuple[int, int], raster: RasterGlyph) -> Point:
    y, x = pixel
    return Point(
        round((x - raster.baseline_x_px) / raster.pixels_per_font_unit, 3),
        round((raster.baseline_y_px - y) / raster.pixels_per_font_unit, 3),
    )


def _point_key(point: Point) -> tuple[float, float]:
    return (-point.y, point.x)
