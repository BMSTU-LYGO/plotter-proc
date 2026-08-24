from __future__ import annotations

import math
from itertools import groupby

from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.routing_cost import RoutingCost, routing_cost

_NEXT_GLYPH_MAX_TRAVEL_PENALTY_MM = 0.35


def optimize_paths(document: PathDocument) -> PathDocument:
    source = [stroke for stroke in document.strokes if isinstance(stroke, PlotterStroke)]
    optimized: list[PlotterStroke] = []
    previous: Point | None = None
    groups = [
        [_copy_stroke(stroke) for stroke in group]
        for _, group in groupby(
            source, key=lambda stroke: stroke.element_id or f"glyph:{stroke.glyph_index}"
        )
    ]
    for group_index, group in enumerate(groups):
        if any(stroke.preserve_order for stroke in group):
            optimized.extend(group)
            previous = group[-1].points[-1]
            continue
        remaining = group
        next_points = (
            _group_endpoints(groups[group_index + 1])
            if group_index + 1 < len(groups)
            else ()
        )
        while remaining:
            selected_index, selected = _nearest_variant(
                remaining,
                previous,
                next_points if len(remaining) == 1 else (),
            )
            remaining.pop(selected_index)
            optimized.append(selected)
            previous = selected.points[-1]
    for index, stroke in enumerate(optimized):
        stroke.id = index
    return PathDocument(
        page_width_mm=document.page_width_mm,
        page_height_mm=document.page_height_mm,
        strokes=optimized,
        warnings=list(document.warnings),
        metadata=dict(document.metadata),
    )


def _nearest_variant(
    strokes: list[PlotterStroke],
    previous: Point | None,
    next_points: tuple[Point, ...] = (),
) -> tuple[int, PlotterStroke]:
    if previous is None:
        return 0, _orient(strokes[0], previous, next_points)
    best_index = 0
    best_stroke = _orient(strokes[0], previous, next_points)
    best_distance = _distance(previous, best_stroke.points[0])
    for index, stroke in enumerate(strokes[1:], start=1):
        candidate = _orient(stroke, previous, next_points)
        distance = _distance(previous, candidate.points[0])
        if distance < best_distance:
            best_index, best_stroke, best_distance = index, candidate, distance
    return best_index, best_stroke


def _orient(
    stroke: PlotterStroke,
    previous: Point | None,
    next_points: tuple[Point, ...] = (),
) -> PlotterStroke:
    candidate = _copy_stroke(stroke)
    if candidate.preserve_order:
        return candidate
    if candidate.closed:
        if previous is None:
            return candidate
        start = min(
            range(len(candidate.points)),
            key=lambda index: _distance(previous, candidate.points[index]),
        )
        candidate.points = candidate.points[start:] + candidate.points[:start]
    else:
        forward = list(candidate.points)
        reverse = list(reversed(candidate.points))
        forward_travel = _distance(previous, forward[0]) if previous else 0.0
        reverse_travel = _distance(previous, reverse[0]) if previous else 0.0
        preferred, alternative = (
            (forward, reverse)
            if forward_travel <= reverse_travel
            else (reverse, forward)
        )
        preferred_travel = min(forward_travel, reverse_travel)
        alternative_travel = max(forward_travel, reverse_travel)
        if next_points and (
            alternative_travel
            <= preferred_travel + _NEXT_GLYPH_MAX_TRAVEL_PENALTY_MM
        ):
            preferred_next = min(_distance(preferred[-1], point) for point in next_points)
            alternative_next = min(
                _distance(alternative[-1], point) for point in next_points
            )
            preferred_cost = routing_cost(
                RoutingCost(
                    travel_distance_mm=preferred_travel,
                    connection_penalty=preferred_next,
                )
            )
            alternative_cost = routing_cost(
                RoutingCost(
                    travel_distance_mm=alternative_travel,
                    connection_penalty=alternative_next,
                )
            )
            if alternative_cost < preferred_cost:
                preferred = alternative
        candidate.points = preferred
    return candidate


def _group_endpoints(strokes: list[PlotterStroke]) -> tuple[Point, ...]:
    return tuple(
        point
        for stroke in strokes
        for point in (stroke.points[0], stroke.points[-1])
        if stroke.points
    )


def _copy_stroke(stroke: PlotterStroke) -> PlotterStroke:
    return PlotterStroke(
        id=stroke.id,
        points=list(stroke.points),
        closed=stroke.closed,
        glyph_index=stroke.glyph_index,
        char=stroke.char,
        contour_index=stroke.contour_index,
        source_glyph_indices=stroke.source_glyph_indices,
        source_chars=stroke.source_chars,
        segment_types=stroke.segment_types,
        word_index=stroke.word_index,
        connection_ids=stroke.connection_ids,
        element_id=stroke.element_id,
        element_type=stroke.element_type,
        font_role=stroke.font_role,
        font_sha256=stroke.font_sha256,
        source_path=stroke.source_path,
        source_page_index=stroke.source_page_index,
        semantic_role=stroke.semantic_role,
        layout_group=stroke.layout_group,
        preserve_order=stroke.preserve_order,
        z_order=stroke.z_order,
    )


def _distance(left: Point, right: Point) -> float:
    return math.hypot(right.x - left.x, right.y - left.y)
