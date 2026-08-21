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
            edge.id,
            edge.start_node_id,
            edge.end_node_id,
            edge.component_id,
            tuple(fixed),
            length,
            edge.closed,
        )
    node_positions = {
        node.id: _point(node.x, node.y, raster)
        for node in nodes
    }
    return normalize_shared_node_endpoints(result, node_positions), warnings


def normalize_shared_node_endpoints(
    edge_geometry: dict[int, SmoothedEdge],
    node_positions: dict[int, Point],
) -> dict[int, SmoothedEdge]:
    """Anchor every edge endpoint to its graph node's canonical coordinate."""
    result: dict[int, SmoothedEdge] = {}
    for edge_id, edge in edge_geometry.items():
        try:
            start = node_positions[edge.start_node_id]
            end = node_positions[edge.end_node_id]
        except KeyError as error:
            raise ValueError(f"Missing canonical position for graph node {error.args[0]}") from error
        points = list(edge.points)
        if not points:
            raise ValueError(f"Edge {edge_id} has no geometry")
        points[0], points[-1] = start, end
        result[edge_id] = SmoothedEdge(
            edge.edge_id,
            edge.start_node_id,
            edge.end_node_id,
            edge.component_id,
            tuple(points),
            edge.length_font_units,
            edge.closed,
        )
    return result


def _point(x: float, y: float, raster: RasterGlyph) -> Point:
    return Point(
        round((x - raster.baseline_x_px) / raster.pixels_per_font_unit, 3),
        round((raster.baseline_y_px - y) / raster.pixels_per_font_unit, 3),
    )
