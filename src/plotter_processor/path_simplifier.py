from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

import numpy as np

from plotter_processor.models import PathDocument, PlotterStroke, Point
from plotter_processor.performance import HotspotTimings

_VECTOR_INTERVAL_THRESHOLD = 64


@dataclass(slots=True)
class SimplificationTemplateCache:
    """Ephemeral per-run cache of translation-equivalent glyph reductions."""

    entries: dict[tuple[object, ...], tuple[tuple[int, ...], float]] = field(
        default_factory=dict
    )


def prime_simplification_template_cache(
    documents: list[PathDocument],
    *,
    duplicate_epsilon_mm: float,
    min_segment_length_mm: float,
    max_deviation_mm: float,
    template_cache: SimplificationTemplateCache,
    template_identities: list[Mapping[int, tuple[object, ...]]],
) -> None:
    """Populate translation-invariant entries in stable page/stroke order."""
    for document, identities in zip(documents, template_identities, strict=True):
        for stroke in document.strokes:
            points = _dedupe(
                stroke.points,
                min(duplicate_epsilon_mm, min_segment_length_mm),
            )
            cache_key = _template_key(stroke, points, max_deviation_mm, identities)
            if cache_key is None or cache_key in template_cache.entries:
                continue
            _, observed, keep_indices = _simplify_stroke_points(
                points, stroke.closed, max_deviation_mm
            )
            template_cache.entries[cache_key] = (keep_indices, observed)


def simplify_path_document(
    document: PathDocument,
    *,
    duplicate_epsilon_mm: float,
    min_segment_length_mm: float,
    max_deviation_mm: float,
    template_cache: SimplificationTemplateCache | None = None,
    template_identities: Mapping[int, tuple[object, ...]] | None = None,
    complexity_before_route: dict[str, int | float] | None = None,
    hotspots: HotspotTimings | None = None,
) -> tuple[PathDocument, dict[str, object]]:
    for value in (duplicate_epsilon_mm, min_segment_length_mm, max_deviation_mm):
        if value < 0 or not math.isfinite(value):
            raise ValueError("simplification tolerances must be finite and non-negative")
    before_complexity = path_complexity(document)
    before = int(before_complexity["point_count"])
    max_seen = 0.0
    simplified_strokes = []
    unique_templates = reused_templates = post_join_strokes = 0
    profile_hotspots = hotspots is not None and hotspots.enabled
    dedupe_ms = rdp_ms = 0.0
    for stroke in document.strokes:
        # RDP owns the geometric error budget. Removing longer micro-segments first can
        # exceed it, so only exact/near-exact duplicates are discarded independently.
        started = time.perf_counter() if profile_hotspots else 0.0
        points = _dedupe(stroke.points, min(duplicate_epsilon_mm, min_segment_length_mm))
        if profile_hotspots:
            dedupe_ms += (time.perf_counter() - started) * 1000.0
        cache_key = _template_key(
            stroke, points, max_deviation_mm, template_identities or {}
        )
        cached = template_cache.entries.get(cache_key) if template_cache and cache_key else None
        if cached is not None:
            keep_indices, observed = cached
            points = [points[index] for index in keep_indices]
            reused_templates += 1
        else:
            started = time.perf_counter() if profile_hotspots else 0.0
            points, observed, keep_indices = _simplify_stroke_points(
                points, stroke.closed, max_deviation_mm
            )
            if profile_hotspots:
                rdp_ms += (time.perf_counter() - started) * 1000.0
            if template_cache is not None and cache_key is not None:
                template_cache.entries[cache_key] = (keep_indices, observed)
                unique_templates += 1
            else:
                post_join_strokes += 1
        max_seen = max(max_seen, observed)
        simplified_strokes.append(replace(stroke, points=points, closed=stroke.closed))
    after = sum(len(stroke.points) for stroke in simplified_strokes)
    result = replace(document, strokes=simplified_strokes, metadata=dict(document.metadata))
    if hotspots is not None and profile_hotspots:
        hotspots.record("simplification.dedupe", dedupe_ms)
        hotspots.record("simplification.rdp", rdp_ms)
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
        "complexity_before_route": complexity_before_route or before_complexity,
        "complexity_after_route": before_complexity,
        "complexity_after_simplification": path_complexity(result),
        "unique_templates_simplified": unique_templates,
        "glyph_occurrences_reused": reused_templates,
        "post_join_strokes_processed": post_join_strokes,
    }
    return result, stats


def path_complexity(document: PathDocument) -> dict[str, int | float]:
    lengths = sorted(len(stroke.points) for stroke in document.strokes)
    point_count = sum(lengths)
    return {
        "stroke_count": len(lengths),
        "point_count": point_count,
        "max_points_per_stroke": lengths[-1] if lengths else 0,
        "median_points_per_stroke": _percentile(lengths, 0.5),
        "p95_points_per_stroke": _percentile(lengths, 0.95),
    }


def _percentile(values: list[int], fraction: float) -> int | float:
    if not values:
        return 0
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 3)


def _template_key(
    stroke: PlotterStroke,
    points: list[Point],
    epsilon: float,
    template_identities: Mapping[int, tuple[object, ...]],
) -> tuple[object, ...] | None:
    if (
        len(stroke.source_glyph_indices) != 1
        or stroke.segment_types != ("glyph",)
        or not points
    ):
        return None
    identity = template_identities.get(stroke.source_glyph_indices[0])
    if identity is None:
        return None
    return (
        *identity,
        stroke.contour_index,
        stroke.closed,
        len(points),
        round(points[-1].x - points[0].x, 12),
        round(points[-1].y - points[0].y, 12),
        round(epsilon, 12),
    )


def _simplify_stroke_points(
    points: list[Point], closed: bool, epsilon: float
) -> tuple[list[Point], float, tuple[int, ...]]:
    source = points
    if closed:
        if points[-1] == points[0]:
            points = points[:-1]
        ring = points + [points[0]]
        keep_indices, observed = _rdp_indices_with_deviation(ring, epsilon)
        if keep_indices[-1] == len(ring) - 1:
            keep_indices = keep_indices[:-1]
        if len(keep_indices) >= 3:
            return [points[index] for index in keep_indices], observed, keep_indices
        return source, 0.0, tuple(range(len(source)))
    keep_indices, observed = _rdp_indices_with_deviation(points, epsilon)
    if len(keep_indices) >= 2:
        return [points[index] for index in keep_indices], observed, keep_indices
    return source, 0.0, tuple(range(len(source)))


def _dedupe(points: list[Point], epsilon: float) -> list[Point]:
    result = [points[0]]
    epsilon_squared = epsilon * epsilon
    for point in points[1:]:
        dx = point.x - result[-1].x
        dy = point.y - result[-1].y
        if dx * dx + dy * dy >= epsilon_squared:
            result.append(point)
    if len(result) == 1 and len(points) > 1:
        result.append(points[-1])
    return result


def _rdp(points: list[Point], epsilon: float) -> list[Point]:
    return _rdp_with_deviation(points, epsilon)[0]


def _rdp_with_deviation(points: list[Point], epsilon: float) -> tuple[list[Point], float]:
    keep, observed = _rdp_indices_with_deviation(points, epsilon)
    return [points[index] for index in keep], observed


def _rdp_indices_with_deviation(
    points: list[Point], epsilon: float
) -> tuple[tuple[int, ...], float]:
    if len(points) <= 2 or epsilon == 0:
        return tuple(range(len(points))), 0.0
    coordinates = np.asarray([(point.x, point.y) for point in points], dtype=np.float64)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    observed_squared = 0.0
    epsilon_squared = epsilon * epsilon
    pending = [(0, len(points) - 1)]
    while pending:
        start_index, end_index = pending.pop()
        start, end = points[start_index], points[end_index]
        dx, dy = end.x - start.x, end.y - start.y
        length_squared = dx * dx + dy * dy
        if end_index - start_index > _VECTOR_INTERVAL_THRESHOLD:
            candidates = coordinates[start_index + 1 : end_index]
            offsets = candidates - coordinates[start_index]
            if length_squared == 0:
                distance_squared = np.einsum("ij,ij->i", offsets, offsets)
            else:
                positions = np.clip(
                    (offsets[:, 0] * dx + offsets[:, 1] * dy) / length_squared,
                    0.0,
                    1.0,
                )
                projections = coordinates[start_index] + positions[:, None] * (dx, dy)
                deltas = candidates - projections
                distance_squared = np.einsum("ij,ij->i", deltas, deltas)
            relative_index = int(np.argmax(distance_squared))
            maximum_squared = float(distance_squared[relative_index])
            maximum_index = start_index + 1 + relative_index
        else:
            maximum_squared = 0.0
            maximum_index = start_index
            for index in range(start_index + 1, end_index):
                point = points[index]
                if length_squared == 0:
                    offset_x = point.x - start.x
                    offset_y = point.y - start.y
                else:
                    position = (
                        (point.x - start.x) * dx + (point.y - start.y) * dy
                    ) / length_squared
                    position = max(0.0, min(1.0, position))
                    offset_x = point.x - (start.x + position * dx)
                    offset_y = point.y - (start.y + position * dy)
                distance_squared = offset_x * offset_x + offset_y * offset_y
                if distance_squared > maximum_squared:
                    maximum_squared = distance_squared
                    maximum_index = index
        if maximum_squared <= epsilon_squared:
            observed_squared = max(observed_squared, maximum_squared)
            continue
        keep[maximum_index] = True
        pending.append((maximum_index, end_index))
        pending.append((start_index, maximum_index))
    return tuple(index for index, retained in enumerate(keep) if retained), math.sqrt(
        observed_squared
    )


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    if dx == dy == 0:
        return math.hypot(point.x - start.x, point.y - start.y)
    t = max(
        0.0, min(1.0, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy))
    )
    projection = Point(start.x + t * dx, start.y + t * dy)
    return math.hypot(point.x - projection.x, point.y - projection.y)
