from __future__ import annotations

import math

from plotter_processor.connection_models import StrokeAnchor
from plotter_processor.models import PlotterStroke, Point


def entry_exit_anchors(
    stroke: PlotterStroke, baseline_y: float
) -> tuple[StrokeAnchor, StrokeAnchor] | None:
    if len(stroke.points) < 2:
        return None
    points = stroke.points
    if stroke.closed:
        opening = min(range(len(points)), key=lambda index: (points[index].x, points[index].y, index))
        points = points[opening:] + points[:opening]
    left_index = min(range(len(points)), key=lambda index: (points[index].x, index))
    right_index = max(range(len(points)), key=lambda index: (points[index].x, -index))
    if left_index == len(points) - 1 or right_index == 0:
        return None
    entry_tangent = _unit(points[left_index], points[left_index + 1])
    exit_tangent = _unit(points[right_index - 1], points[right_index])
    entry = StrokeAnchor(
        points[left_index], entry_tangent, "left", "entry", 0.9, stroke.id, left_index,
        points[left_index].y - baseline_y,
    )
    exit = StrokeAnchor(
        points[right_index], exit_tangent, "right", "exit", 0.9, stroke.id, right_index,
        points[right_index].y - baseline_y,
    )
    return entry, exit


def _unit(a: Point, b: Point) -> Point:
    length = math.hypot(b.x - a.x, b.y - a.y)
    return Point((b.x - a.x) / max(length, 1e-9), (b.y - a.y) / max(length, 1e-9))
