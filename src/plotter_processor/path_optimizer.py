from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import groupby, pairwise

from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.routing_cost import RoutingCost, routing_cost

_NEXT_GLYPH_MAX_TRAVEL_PENALTY_MM = 0.35


@dataclass(frozen=True, slots=True)
class RetraceConfig:
    enabled: bool = True
    max_length_mm: float = 1.2
    max_repeats: int = 1
    allowed_segment_types: frozenset[str] = frozenset({"glyph"})


def load_retrace_config(values: Mapping[str, object]) -> RetraceConfig:
    enabled = values.get("enabled", True)
    max_length = values.get("max_length_mm", 1.2)
    max_repeats = values.get("max_repeats", 1)
    allowed = values.get("allowed_segment_types", ["glyph"])
    if not isinstance(enabled, bool):
        raise TypeError("handwriting.retrace.enabled must be boolean")
    if isinstance(max_length, bool) or not isinstance(max_length, (int, float)):
        raise TypeError("handwriting.retrace.max_length_mm must be numeric")
    if isinstance(max_repeats, bool) or not isinstance(max_repeats, int):
        raise TypeError("handwriting.retrace.max_repeats must be an integer")
    if float(max_length) < 0 or not 0 <= max_repeats <= 2:
        raise ValueError("Invalid handwriting retrace limits")
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise TypeError("handwriting.retrace.allowed_segment_types must be a list")
    return RetraceConfig(
        enabled,
        min(1.2, float(max_length)),
        min(1, max_repeats),
        frozenset(allowed),
    )


def optimize_paths(
    document: PathDocument, retrace_config: RetraceConfig | None = None
) -> PathDocument:
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
    optimized, retrace_report = _apply_safe_retrace(
        optimized, retrace_config or RetraceConfig()
    )
    for index, stroke in enumerate(optimized):
        stroke.id = index
    metadata = dict(document.metadata)
    metadata["safe_retrace"] = retrace_report
    return PathDocument(
        page_width_mm=document.page_width_mm,
        page_height_mm=document.page_height_mm,
        strokes=optimized,
        warnings=list(document.warnings),
        metadata=metadata,
    )


def _apply_safe_retrace(
    strokes: list[PlotterStroke], config: RetraceConfig
) -> tuple[list[PlotterStroke], dict[str, float | int | bool]]:
    if not config.enabled or config.max_repeats == 0:
        return strokes, {
            "retrace_enabled": False,
            "retrace_merges": 0,
            "retrace_pen_lifts_saved": 0,
            "retrace_distance_mm": 0.0,
        }
    result: list[PlotterStroke] = []
    merges = 0
    retraced_distance = 0.0
    repeats: dict[int, int] = {}
    for stroke in strokes:
        if not result:
            result.append(stroke)
            continue
        previous = result[-1]
        merged = _merge_by_safe_retrace(previous, stroke, config, repeats)
        if merged is None:
            result.append(stroke)
            continue
        combined, distance = merged
        result[-1] = combined
        merges += 1
        retraced_distance += distance
    return result, {
        "retrace_enabled": True,
        "retrace_merges": merges,
        "retrace_pen_lifts_saved": merges,
        "retrace_distance_mm": round(retraced_distance, 6),
    }


def _merge_by_safe_retrace(
    previous: PlotterStroke,
    following: PlotterStroke,
    config: RetraceConfig,
    repeats: dict[int, int],
) -> tuple[PlotterStroke, float] | None:
    if (
        previous.glyph_index is None
        or previous.glyph_index != following.glyph_index
        or previous.closed
        or following.closed
        or len(previous.points) < 2
        or len(following.points) < 2
        or not _segments_allow_retrace(previous, config)
        or not _segments_allow_retrace(following, config)
        or repeats.get(previous.glyph_index, 0) >= config.max_repeats
    ):
        return None
    matches: list[tuple[float, int, bool]] = []
    for index, point in enumerate(previous.points[:-1]):
        distance = _polyline_length(previous.points[index:])
        if distance > config.max_length_mm + 1e-9:
            continue
        if _distance(point, following.points[0]) <= 1e-6:
            matches.append((distance, index, False))
        if not following.preserve_order and _distance(point, following.points[-1]) <= 1e-6:
            matches.append((distance, index, True))
    if not matches:
        return None
    distance, junction_index, reverse_following = min(matches)
    following_points = (
        list(reversed(following.points))
        if reverse_following
        else list(following.points)
    )
    retrace_points = list(reversed(previous.points[junction_index:]))
    points = [*previous.points, *retrace_points[1:], *following_points[1:]]
    repeats[previous.glyph_index] = repeats.get(previous.glyph_index, 0) + 1
    return (
        replace(
            previous,
            points=points,
            segment_types=previous.segment_types
            + ("retrace",)
            + following.segment_types,
            source_glyph_indices=tuple(
                dict.fromkeys(
                    previous.source_glyph_indices
                    + following.source_glyph_indices
                )
            ),
            source_chars=previous.source_chars or following.source_chars,
            preserve_order=True,
        ),
        distance,
    )


def _segments_allow_retrace(stroke: PlotterStroke, config: RetraceConfig) -> bool:
    kinds = set(stroke.segment_types) or {"glyph"}
    return kinds <= config.allowed_segment_types


def _polyline_length(points: list[Point]) -> float:
    return sum(_distance(first, second) for first, second in pairwise(points))


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
