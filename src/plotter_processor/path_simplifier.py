from __future__ import annotations

import math
from dataclasses import replace

from plotter_processor.models import PathDocument, Point


def simplify_path_document(
    document: PathDocument,
    *,
    duplicate_epsilon_mm: float,
    min_segment_length_mm: float,
    max_deviation_mm: float,
) -> tuple[PathDocument, dict[str, object]]:
    for value in (duplicate_epsilon_mm, min_segment_length_mm, max_deviation_mm):
        if value < 0 or not math.isfinite(value):
            raise ValueError("simplification tolerances must be finite and non-negative")
    before = sum(len(stroke.points) for stroke in document.strokes)
    max_seen = 0.0
    simplified_strokes = []
    for stroke in document.strokes:
        # RDP owns the geometric error budget. Removing longer micro-segments first can
        # exceed it, so only exact/near-exact duplicates are discarded independently.
        points = _dedupe(stroke.points, min(duplicate_epsilon_mm, min_segment_length_mm))
        closed = stroke.closed
        if closed:
            if points[-1] == points[0]:
                points = points[:-1]
            ring = points + [points[0]]
            reduced, observed = _rdp_with_deviation(ring, max_deviation_mm)
            if reduced[-1] == reduced[0]:
                reduced = reduced[:-1]
            if len(reduced) >= 3:
                points = reduced
            else:
                observed = 0.0
        else:
            reduced, observed = _rdp_with_deviation(points, max_deviation_mm)
            if len(reduced) >= 2:
                points = reduced
            else:
                observed = 0.0
        max_seen = max(max_seen, observed)
        simplified_strokes.append(replace(stroke, points=points, closed=closed))
    after = sum(len(stroke.points) for stroke in simplified_strokes)
    result = replace(document, strokes=simplified_strokes, metadata=dict(document.metadata))
    stats = {
        "enabled": True,
        "points_before_simplification": before,
        "points_after_simplification": after,
        "segments_before_simplification": sum(
            max(0, len(s.points) - 1) + int(s.closed) for s in document.strokes
        ),
        "segments_after_simplification": sum(
            max(0, len(s.points) - 1) + int(s.closed) for s in simplified_strokes
        ),
        "point_reduction_ratio": round((before - after) / before, 6) if before else 0,
        "max_observed_deviation_mm": round(max_seen, 6),
    }
    return result, stats


def _dedupe(points: list[Point], epsilon: float) -> list[Point]:
    result = [points[0]]
    for point in points[1:]:
        if math.hypot(point.x - result[-1].x, point.y - result[-1].y) >= epsilon:
            result.append(point)
    if len(result) == 1 and len(points) > 1:
        result.append(points[-1])
    return result


def _rdp(points: list[Point], epsilon: float) -> list[Point]:
    return _rdp_with_deviation(points, epsilon)[0]


def _rdp_with_deviation(points: list[Point], epsilon: float) -> tuple[list[Point], float]:
    if len(points) <= 2 or epsilon == 0:
        return points, 0.0
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    observed = 0.0
    pending = [(0, len(points) - 1)]
    while pending:
        start_index, end_index = pending.pop()
        start, end = points[start_index], points[end_index]
        dx, dy = end.x - start.x, end.y - start.y
        length_squared = dx * dx + dy * dy
        maximum = 0.0
        maximum_index = start_index
        for index in range(start_index + 1, end_index):
            point = points[index]
            if length_squared == 0:
                distance = math.hypot(point.x - start.x, point.y - start.y)
            else:
                position = (
                    (point.x - start.x) * dx + (point.y - start.y) * dy
                ) / length_squared
                position = max(0.0, min(1.0, position))
                distance = math.hypot(
                    point.x - (start.x + position * dx),
                    point.y - (start.y + position * dy),
                )
            if distance > maximum:
                maximum = distance
                maximum_index = index
        if maximum <= epsilon:
            observed = max(observed, maximum)
            continue
        keep[maximum_index] = True
        pending.append((maximum_index, end_index))
        pending.append((start_index, maximum_index))
    return [point for index, point in enumerate(points) if keep[index]], observed


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    if dx == dy == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    t = max(
        0.0, min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy))
    )
    projection = Point(start.x + t * dx, start.y + t * dy)
    return math.hypot(point.x - projection.x, point.y - projection.y)
