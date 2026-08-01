from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.models import SmoothedEdge
from plotter_processor.centerline_font.route_assembler import assemble_component_route
from plotter_processor.centerline_font.route_planner import plan_glyph_routes
from plotter_processor.centerline_font.skeleton_graph import build_skeleton_graph
from plotter_processor.centerline_font.skeletonizer import build_skeleton, prune_short_spurs
from plotter_processor.models import PlotterStroke, Point


@dataclass(frozen=True, slots=True)
class RasterCenterlineConfig:
    threshold: int = 160
    closing_radius_px: int = 1
    min_component_length_mm: float = 0.20
    simplify_tolerance_mm: float = 0.025
    min_branch_width_factor: float = 0.35
    max_coverage_loss: float = 0.01
    max_render_pixels: int = 16_000_000
    max_components: int = 5_000
    max_nodes: int = 150_000
    max_edges: int = 150_000
    max_points: int = 150_000
    max_retrace_ratio: float = 0.65
    min_coverage_ratio: float = 0.45
    strict_quality: bool = False


@dataclass(frozen=True, slots=True)
class CenterlineGeometry:
    strokes: tuple[PlotterStroke, ...]
    components: int
    graph_edges: int
    junctions: int
    pen_lifts: int
    retraced_length_mm: float
    warnings: tuple[str, ...]
    quality: dict[str, object] = field(default_factory=dict)
    mask: np.ndarray | None = field(default=None, repr=False, compare=False)
    skeleton: np.ndarray | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _RoutingConfig:
    routing_strategy: str = "one_stroke_per_component"
    max_retrace_ratio: float = 0.65
    fallback_strategy: str = "minimum_strokes"


def raster_to_centerline(
    binary_mask: np.ndarray,
    pixel_to_mm: float | tuple[float, float],
    config: RasterCenterlineConfig | None = None,
) -> CenterlineGeometry:
    options = config or RasterCenterlineConfig()
    mask = np.asarray(binary_mask, dtype=bool)
    if mask.ndim != 2 or not mask.size:
        raise ValueError("Centerline mask must be a non-empty 2D array")
    if mask.size > options.max_render_pixels:
        raise ValueError(
            f"Centerline mask has {mask.size} pixels; limit is {options.max_render_pixels}"
        )
    scale_x, scale_y = _pixel_scale(pixel_to_mm)
    if options.closing_radius_px:
        structure = _disk(options.closing_radius_px)
        mask = ndimage.binary_closing(mask, structure=structure)
    _, components_before = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    if components_before > options.max_components:
        raise ValueError(
            f"Centerline mask has {components_before} components; limit is {options.max_components}"
        )
    skeleton_result = build_skeleton(mask, method="skeletonize")
    skeleton = prune_short_spurs(
        skeleton_result.mask,
        skeleton_result.distance,
        min_branch_width_factor=options.min_branch_width_factor,
        ink_mask=mask,
        max_coverage_loss=options.max_coverage_loss,
        preserve_connector_terminals=True,
    )
    skeleton, removed = _remove_tiny_components(
        skeleton, scale_x, scale_y, options.min_component_length_mm
    )
    if not skeleton.any():
        raise ValueError("Centerline conversion removed all formula ink")
    nodes, edges = build_skeleton_graph(skeleton, suppress_corner_diagonals=True)
    if len(nodes) > options.max_nodes or len(edges) > options.max_edges:
        raise ValueError(
            "Centerline graph exceeds complexity limit: "
            f"nodes={len(nodes)}, edges={len(edges)}"
        )
    routing = _RoutingConfig(max_retrace_ratio=options.max_retrace_ratio)
    routes = plan_glyph_routes(nodes, edges, routing)  # type: ignore[arg-type]
    edge_geometry = {
        edge.id: SmoothedEdge(
            edge.id,
            edge.start_node_id,
            edge.end_node_id,
            edge.component_id,
            tuple(Point(pixel[1] * scale_x, pixel[0] * scale_y) for pixel in edge.pixels),
            edge.length_px * math.sqrt(scale_x * scale_y),
            edge.closed,
        )
        for edge in edges
    }
    strokes: list[PlotterStroke] = []
    retraced = 0.0
    for route in routes:
        assembled = assemble_component_route(route, edge_geometry)
        points = _simplify(list(assembled.points), options.simplify_tolerance_mm)
        if len(set(points)) < 2:
            continue
        strokes.append(PlotterStroke(len(strokes), points, assembled.closed))
        retraced += assembled.retraced_length_font_units
    point_count = sum(len(stroke.points) for stroke in strokes)
    if point_count > options.max_points:
        raise ValueError(f"Centerline output has {point_count} points; limit is {options.max_points}")
    if not strokes:
        raise ValueError("Centerline conversion produced no drawable strokes")
    components_after = len({route.component_id for route in routes})
    draw_length = sum(_stroke_length(stroke) for stroke in strokes)
    radii = skeleton_result.distance[skeleton]
    radius = max(1, round(float(np.median(radii)))) if radii.size else 1
    reconstructed = ndimage.binary_dilation(skeleton, iterations=radius)
    coverage = float((reconstructed & mask).sum()) / max(1, int(mask.sum()))
    retrace_ratio = retraced / max(draw_length, 1e-9)
    warnings: list[str] = []
    if components_after > 100:
        warnings.append("latex_centerline_many_components")
    if retrace_ratio > options.max_retrace_ratio:
        warnings.append("latex_centerline_high_retrace")
    if coverage < options.min_coverage_ratio:
        warnings.append("latex_centerline_low_coverage")
    if removed:
        warnings.append("latex_centerline_tiny_symbols_removed")
    quality: dict[str, object] = {
        "mask_foreground_pixels": int(mask.sum()),
        "components_before_pruning": int(components_before),
        "components_after_pruning": components_after,
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "junction_count": sum(node.kind == "junction" for node in nodes),
        "strokes": len(strokes),
        "points": point_count,
        "draw_length_mm": round(draw_length, 6),
        "retraced_length_mm": round(retraced, 6),
        "retrace_ratio": round(retrace_ratio, 6),
        "small_components_removed": removed,
        "centerline_coverage_ratio": round(coverage, 6),
        "needs_review": bool(warnings),
    }
    if options.strict_quality and warnings:
        raise ValueError("LaTeX centerline quality gate failed: " + ", ".join(warnings))
    return CenterlineGeometry(
        tuple(strokes), components_after, len(edges), int(quality["junction_count"]),
        len(strokes), retraced, tuple(warnings), quality, mask, skeleton,
    )


def _pixel_scale(value: float | tuple[float, float]) -> tuple[float, float]:
    values = (value, value) if isinstance(value, (int, float)) else value
    if len(values) != 2 or any(not math.isfinite(float(item)) or item <= 0 for item in values):
        raise ValueError("pixel_to_mm must contain finite positive values")
    return float(values[0]), float(values[1])


def _disk(radius: int) -> np.ndarray:
    y, x = np.ogrid[-radius : radius + 1, -radius : radius + 1]
    return x * x + y * y <= radius * radius


def _remove_tiny_components(
    skeleton: np.ndarray, scale_x: float, scale_y: float, minimum_mm: float
) -> tuple[np.ndarray, int]:
    if minimum_mm <= 0:
        return skeleton, 0
    labels, count = ndimage.label(skeleton, structure=np.ones((3, 3), dtype=np.uint8))
    result = skeleton.copy()
    removed = 0
    pixel_size = math.sqrt(scale_x * scale_y)
    for label in range(1, count + 1):
        component = labels == label
        # Preserve dots and short horizontal math bars when their ink is substantial.
        ys, xs = np.nonzero(component)
        diagonal = math.hypot(float(np.ptp(xs)), float(np.ptp(ys))) * pixel_size
        if diagonal < minimum_mm and int(component.sum()) <= 2:
            result[component] = False
            removed += 1
    return result, removed


def _simplify(points: list[Point], tolerance: float) -> list[Point]:
    if len(points) <= 2 or tolerance <= 0:
        return points
    start, end = points[0], points[-1]
    distance, index = max(
        ((_point_segment_distance(point, start, end), offset) for offset, point in enumerate(points[1:-1], 1)),
        default=(0.0, 0),
    )
    if distance <= tolerance:
        return [start, end]
    return [*_simplify(points[: index + 1], tolerance)[:-1], *_simplify(points[index:], tolerance)]


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    if dx == 0 and dy == 0:
        return math.dist((point.x, point.y), (start.x, start.y))
    factor = max(0.0, min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)))
    projection = (start.x + factor * dx, start.y + factor * dy)
    return math.dist((point.x, point.y), projection)


def _stroke_length(stroke: PlotterStroke) -> float:
    length = sum(
        math.dist((left.x, left.y), (right.x, right.y))
        for left, right in pairwise(stroke.points)
    )
    if stroke.closed and len(stroke.points) > 2:
        length += math.dist(
            (stroke.points[-1].x, stroke.points[-1].y),
            (stroke.points[0].x, stroke.points[0].y),
        )
    return length
