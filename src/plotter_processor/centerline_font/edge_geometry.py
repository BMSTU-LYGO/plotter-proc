from __future__ import annotations

import math
from itertools import pairwise

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.models import (
    CenterlineStroke,
    RasterGlyph,
    SkeletonEdge,
    SkeletonNode,
    SmoothedEdge,
)
from plotter_processor.centerline_font.stroke_smoother import smooth_strokes
from plotter_processor.models import Point


def build_smoothed_edge_geometry(
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    raster: RasterGlyph,
    config: CenterlineConfig,
) -> tuple[dict[int, SmoothedEdge], list[str]]:
    node_map = {node.id: node for node in nodes}
    result: dict[int, SmoothedEdge] = {}
    warnings: list[str] = []
    for edge in edges:
        points = [_point(pixel[1], pixel[0], raster) for pixel in edge.pixels]
        points[0] = _point(node_map[edge.start_node_id].x, node_map[edge.start_node_id].y, raster)
        points[-1] = _point(node_map[edge.end_node_id].x, node_map[edge.end_node_id].y, raster)
        smoothed, edge_warnings = smooth_strokes(
            [CenterlineStroke(edge.id, tuple(points), edge.closed, edge.component_id)],
            simplify_tolerance=config.simplify_tolerance_px / raster.pixels_per_font_unit,
            smoothing_factor=config.spline_smoothing_factor,
            output_step=config.output_step_px / raster.pixels_per_font_unit,
            max_points=config.max_points_per_stroke,
        )
        warnings.extend(edge_warnings)
        if not smoothed:
            smoothed = [CenterlineStroke(edge.id, tuple(points), edge.closed, edge.component_id)]
        geometry = smoothed[0]
        fixed = list(geometry.points)
        fixed[0], fixed[-1] = points[0], points[-1]
        length = sum(math.hypot(b.x - a.x, b.y - a.y) for a, b in pairwise(fixed))
        result[edge.id] = SmoothedEdge(
            edge.id, edge.start_node_id, edge.end_node_id, edge.component_id,
            tuple(fixed), length, edge.closed,
        )
    return result, warnings


def _point(x: float, y: float, raster: RasterGlyph) -> Point:
    return Point(
        round((x - raster.baseline_x_px) / raster.pixels_per_font_unit, 3),
        round((raster.baseline_y_px - y) / raster.pixels_per_font_unit, 3),
    )
