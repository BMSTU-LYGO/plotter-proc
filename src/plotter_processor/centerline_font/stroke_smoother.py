from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
from scipy.interpolate import splev, splprep

from plotter_processor.centerline_font.models import CenterlineStroke
from plotter_processor.models import Point


def smooth_strokes(
    strokes: list[CenterlineStroke],
    *,
    simplify_tolerance: float,
    smoothing_factor: float,
    output_step: float,
    max_points: int,
) -> tuple[list[CenterlineStroke], list[str]]:
    output: list[CenterlineStroke] = []
    warnings: list[str] = []
    for stroke in strokes:
        points = _dedupe(stroke.points)
        if len(points) < (3 if stroke.closed else 2):
            continue
        simplified = _rdp(points, simplify_tolerance)
        if len(simplified) >= (4 if stroke.closed else 3) and smoothing_factor > 0:
            simplified = _spline(simplified, stroke.closed, smoothing_factor, output_step)
        tolerance = simplify_tolerance
        while len(simplified) > max_points:
            tolerance = max(0.01, tolerance * 1.5)
            simplified = _rdp(simplified, tolerance)
        if tolerance != simplify_tolerance:
            warnings.append(f"Stroke {stroke.id} simplified to respect point limit")
        if not stroke.closed:
            simplified[0], simplified[-1] = points[0], points[-1]
        output.append(
            CenterlineStroke(
                len(output),
                tuple(Point(round(p.x, 3), round(p.y, 3)) for p in simplified),
                stroke.closed,
            )
        )
    return output, warnings


def _dedupe(points: tuple[Point, ...] | list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


def _rdp(points: list[Point], epsilon: float) -> list[Point]:
    if len(points) <= 2 or epsilon <= 0:
        return list(points)
    start, end = points[0], points[-1]
    dx, dy = end.x - start.x, end.y - start.y
    denominator = math.hypot(dx, dy)
    distances = [
        math.hypot(p.x - start.x, p.y - start.y)
        if denominator == 0
        else abs(dy * p.x - dx * p.y + end.x * start.y - end.y * start.x)
        / denominator
        for p in points[1:-1]
    ]
    if not distances or max(distances) <= epsilon:
        return [start, end]
    index = distances.index(max(distances)) + 1
    return _rdp(points[: index + 1], epsilon)[:-1] + _rdp(points[index:], epsilon)


def _spline(points: list[Point], closed: bool, factor: float, step: float) -> list[Point]:
    xy = np.array([(p.x, p.y) for p in points], dtype=float).T
    try:
        tck, _ = splprep(xy, s=factor * len(points), per=closed, k=min(3, len(points) - 1))
        length = sum(math.hypot(b.x - a.x, b.y - a.y) for a, b in pairwise(points))
        count = max(len(points), math.ceil(length / max(step, 0.001)) + 1)
        values = np.linspace(0, 1, count, endpoint=not closed)
        x, y = splev(values, tck)
        return [Point(float(px), float(py)) for px, py in zip(x, y, strict=True)]
    except (TypeError, ValueError):
        return points
