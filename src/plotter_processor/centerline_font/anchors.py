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
    if not stroke.closed:
        if points[0].x <= points[-1].x:
            entry_index, exit_index = 0, len(points) - 1
        else:
            entry_index, exit_index = len(points) - 1, 0
        entry_tangent = _terminal_tangent(points, entry_index, toward_stroke=True)
        exit_tangent = _terminal_tangent(points, exit_index, toward_stroke=False)
        routeable = (
            entry_tangent.x >= -0.15
            and exit_tangent.x >= -0.15
            and points[exit_index].x >= points[entry_index].x
        )
        entry = StrokeAnchor(
            points[entry_index],
            entry_tangent,
            "left",
            "entry",
            _anchor_confidence(points[entry_index], baseline_y, routeable),
            stroke.id,
            entry_index,
            points[entry_index].y - baseline_y,
            "terminal",
            routeable,
        )
        exit = StrokeAnchor(
            points[exit_index],
            exit_tangent,
            "right",
            "exit",
            _anchor_confidence(points[exit_index], baseline_y, routeable),
            stroke.id,
            exit_index,
            points[exit_index].y - baseline_y,
            "terminal",
            routeable,
        )
        return entry, exit
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
        "side_extreme",
        False,
    )
    exit = StrokeAnchor(
        points[right_index], exit_tangent, "right", "exit", 0.9, stroke.id, right_index,
        points[right_index].y - baseline_y,
        "side_extreme",
        False,
    )
    return entry, exit


def _unit(a: Point, b: Point) -> Point:
    length = math.hypot(b.x - a.x, b.y - a.y)
    return Point((b.x - a.x) / max(length, 1e-9), (b.y - a.y) / max(length, 1e-9))


def _terminal_tangent(
    points: list[Point], anchor_index: int, *, toward_stroke: bool
) -> Point:
    direction = 1 if anchor_index == 0 else -1
    target_index = anchor_index
    distance = 0.0
    while 0 <= target_index + direction < len(points) and distance < 0.8:
        next_index = target_index + direction
        distance += math.hypot(
            points[next_index].x - points[target_index].x,
            points[next_index].y - points[target_index].y,
        )
        target_index = next_index
    tangent = _unit(points[anchor_index], points[target_index])
    if toward_stroke:
        return tangent
    return Point(-tangent.x, -tangent.y)


def _anchor_confidence(point: Point, baseline_y: float, connectable: bool) -> float:
    if not connectable:
        return 0.25
    return max(0.55, 1.0 - abs(point.y - baseline_y) * 0.08)
