from __future__ import annotations

import hashlib
import json
import math
import random
import time
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

from plotter_processor.centerline_font.anchors import entry_exit_anchors
from plotter_processor.centerline_font.stroke_roles import classify_strokes
from plotter_processor.connection_models import GlyphConnectionCandidate, StrokeAnchor
from plotter_processor.models import PathDocument, PlotterStroke, Point, PositionedGlyph
from plotter_processor.performance import HotspotTimings


@dataclass(frozen=True, slots=True)
class JoiningConfig:
    enabled: bool
    max_join_gap_mm: float
    max_join_angle_deg: float
    connector_step_mm: float
    do_not_join_before: frozenset[str]
    do_not_join_after: frozenset[str]
    lift_between_words: bool
    mode: str = "safe"
    max_vertical_offset_mm: float = 1.2
    connect_letters_only: bool = True
    min_corridor_inside_ratio: float = 0.75
    allow_connector_outside_ink: bool = True
    outside_ink_margin_mm: float = 0.35
    contact_epsilon_mm: float = 0.08
    collision_clearance_mm: float = 0.10


@dataclass(frozen=True, slots=True)
class VariationConfig:
    enabled: bool
    seed: int
    baseline_jitter_mm: float
    rotation_deg: float
    scale_percent: float
    spacing_jitter_mm: float


@dataclass(frozen=True, slots=True)
class GlyphVariation:
    glyph_variant: int
    scale_x: float
    scale_y: float
    rotation_deg: float
    baseline_offset_mm: float
    spacing_adjustment_mm: float
    variant_slant: float
    cosine: float
    sine: float


@dataclass(frozen=True, slots=True)
class HandwritingVariationContext:
    seed: int
    glyphs: dict[int, GlyphVariation]

    def for_glyph(self, glyph_index: int) -> GlyphVariation:
        return self.glyphs[glyph_index]


_MAX_GLYPH_SCALE_PERCENT = 3.0
_MAX_GLYPH_ROTATION_DEG = 2.0
_MAX_BASELINE_OFFSET_MM = 0.25


@dataclass(frozen=True, slots=True)
class _GlyphRoute:
    glyph: PositionedGlyph
    main: PlotterStroke | None
    entry: StrokeAnchor | None
    exit: StrokeAnchor | None


@dataclass(frozen=True, slots=True)
class _SegmentObstacle:
    stroke: PlotterStroke
    segment_index: int
    first: Point
    second: Point
    bounds: tuple[float, float, float, float]


@dataclass(slots=True)
class _StrokeSegmentIndex:
    segments: tuple[_SegmentObstacle, ...]
    cell_size_mm: float
    cells: dict[tuple[int, int], tuple[int, ...]]

    @classmethod
    def build(
        cls, stroke: PlotterStroke, *, cell_size_mm: float
    ) -> _StrokeSegmentIndex:
        segments = tuple(
            _segment_obstacle(stroke, segment_index, first, second)
            for segment_index, (first, second) in enumerate(pairwise(stroke.points))
        )
        cells: dict[tuple[int, int], list[int]] = {}
        for segment_index, segment in enumerate(segments):
            min_x, min_y, max_x, max_y = segment.bounds
            for cell_x in range(
                math.floor(min_x / cell_size_mm),
                math.floor(max_x / cell_size_mm) + 1,
            ):
                for cell_y in range(
                    math.floor(min_y / cell_size_mm),
                    math.floor(max_y / cell_size_mm) + 1,
                ):
                    cells.setdefault((cell_x, cell_y), []).append(segment_index)
        return cls(
            segments,
            cell_size_mm,
            {cell: tuple(indices) for cell, indices in cells.items()},
        )

    def query(
        self, bounds: tuple[float, float, float, float]
    ) -> list[_SegmentObstacle]:
        min_x, min_y, max_x, max_y = bounds
        matches: set[int] = set()
        for cell_x in range(
            math.floor(min_x / self.cell_size_mm),
            math.floor(max_x / self.cell_size_mm) + 1,
        ):
            for cell_y in range(
                math.floor(min_y / self.cell_size_mm),
                math.floor(max_y / self.cell_size_mm) + 1,
            ):
                matches.update(self.cells.get((cell_x, cell_y), ()))
        return [
            self.segments[index]
            for index in sorted(matches)
            if _bounds_overlap(bounds, self.segments[index].bounds)
        ]


@dataclass(slots=True)
class _SegmentObstacleIndex:
    strokes: list[PlotterStroke]
    stroke_bounds: list[tuple[float, float, float, float]]
    cell_size_mm: float
    segment_cell_size_mm: float
    cells: dict[tuple[int, int], tuple[int, ...]]
    segment_cache: dict[int, _StrokeSegmentIndex]

    @classmethod
    def build(
        cls,
        strokes: list[PlotterStroke],
        *,
        cell_size_mm: float = 4.0,
        segment_cell_size_mm: float = 0.5,
    ) -> _SegmentObstacleIndex:
        stroke_bounds = [_stroke_bounds(stroke) for stroke in strokes]
        cells: dict[tuple[int, int], list[int]] = {}
        for index, bounds in enumerate(stroke_bounds):
            min_x, min_y, max_x, max_y = bounds
            for cell_x in range(math.floor(min_x / cell_size_mm), math.floor(max_x / cell_size_mm) + 1):
                for cell_y in range(math.floor(min_y / cell_size_mm), math.floor(max_y / cell_size_mm) + 1):
                    cells.setdefault((cell_x, cell_y), []).append(index)
        return cls(
            strokes,
            stroke_bounds,
            cell_size_mm,
            segment_cell_size_mm,
            {cell: tuple(indices) for cell, indices in cells.items()},
            {},
        )

    def query(
        self, bounds: tuple[float, float, float, float]
    ) -> list[_SegmentObstacle]:
        min_x, min_y, max_x, max_y = bounds
        matches: set[int] = set()
        for cell_x in range(
            math.floor(min_x / self.cell_size_mm),
            math.floor(max_x / self.cell_size_mm) + 1,
        ):
            for cell_y in range(
                math.floor(min_y / self.cell_size_mm),
                math.floor(max_y / self.cell_size_mm) + 1,
            ):
                matches.update(self.cells.get((cell_x, cell_y), ()))
        segments: list[_SegmentObstacle] = []
        for stroke_index in sorted(matches):
            if not _bounds_overlap(bounds, self.stroke_bounds[stroke_index]):
                continue
            cached = self.segment_cache.get(stroke_index)
            if cached is None:
                cached = _StrokeSegmentIndex.build(
                    self.strokes[stroke_index],
                    cell_size_mm=self.segment_cell_size_mm,
                )
                self.segment_cache[stroke_index] = cached
            segments.extend(cached.query(bounds))
        return segments


@dataclass(slots=True)
class _ConnectionCounters:
    cheap_rejected_pairs: int = 0
    solver_calls: int = 0
    beziers_built: int = 0
    collision_queries: int = 0
    segments_tested: int = 0


def load_variation_config(root: Mapping[str, object]) -> VariationConfig:
    values = _mapping(_mapping(root, "handwriting"), "variation")
    seed = values.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("handwriting.variation.seed must be an integer")
    return VariationConfig(
        _boolean(values, "enabled"),
        seed,
        _nonnegative(values, "baseline_jitter_mm"),
        _nonnegative(values, "rotation_deg"),
        _nonnegative(values, "scale_percent"),
        _nonnegative(values, "spacing_jitter_mm"),
    )


def build_variation_context(
    glyphs: list[PositionedGlyph], config: VariationConfig
) -> HandwritingVariationContext:
    occurrences: dict[str, int] = {}
    variations: dict[int, GlyphVariation] = {}
    for glyph in glyphs:
        occurrence = occurrences.get(glyph.char, 0)
        occurrences[glyph.char] = occurrence + 1
        rng = random.Random(_variation_seed(config.seed, glyph))
        rotation_limit = min(config.rotation_deg, _MAX_GLYPH_ROTATION_DEG)
        scale_limit = min(config.scale_percent, _MAX_GLYPH_SCALE_PERCENT) / 100
        baseline_limit = min(
            config.baseline_jitter_mm,
            _MAX_BASELINE_OFFSET_MM,
            max(0.05, glyph.advance_mm * 0.06),
        )
        angle = rng.uniform(-rotation_limit, rotation_limit)
        variant = (_variation_seed(config.seed, glyph.char) + occurrence) % 3
        variations[glyph.glyph_index] = GlyphVariation(
            glyph_variant=variant,
            scale_x=1 + rng.uniform(-scale_limit, scale_limit),
            scale_y=1 + rng.uniform(-scale_limit, scale_limit),
            rotation_deg=angle,
            baseline_offset_mm=rng.uniform(
                -baseline_limit, baseline_limit
            ),
            spacing_adjustment_mm=rng.uniform(
                -config.spacing_jitter_mm, config.spacing_jitter_mm
            ),
            variant_slant=(-0.012, 0.0, 0.012)[variant],
            cosine=math.cos(math.radians(angle)),
            sine=math.sin(math.radians(angle)),
        )
    return HandwritingVariationContext(config.seed, variations)


def _variation_seed(seed: int, glyph: PositionedGlyph | str) -> int:
    identity = (
        glyph
        if isinstance(glyph, str)
        else f"{glyph.glyph_index}:{glyph.char}:{glyph.line_index}:{glyph.word_index}"
    )
    digest = hashlib.blake2b(f"{seed}:{identity}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def apply_variation(
    document: PathDocument,
    glyphs: list[PositionedGlyph],
    config: VariationConfig,
    *,
    hotspots: HotspotTimings | None = None,
) -> PathDocument:
    if not config.enabled:
        return document
    started = time.perf_counter() if hotspots and hotspots.enabled else None
    positions = {glyph.glyph_index: glyph for glyph in glyphs}
    context = build_variation_context(glyphs, config)
    varied: list[PlotterStroke] = []
    for stroke in document.strokes:
        index = stroke.glyph_index
        glyph = positions.get(index) if index is not None else None
        if glyph is None:
            varied.append(stroke)
            continue
        transform = context.for_glyph(index)
        points = []
        for point in stroke.points:
            x, y = point.x - glyph.x_mm, point.y - glyph.baseline_y_mm
            variant_x = x + transform.variant_slant * y
            points.append(
                Point(
                    glyph.x_mm
                    + transform.spacing_adjustment_mm
                    + transform.scale_x
                    * (variant_x * transform.cosine - y * transform.sine),
                    glyph.baseline_y_mm
                    + transform.baseline_offset_mm
                    + transform.scale_y
                    * (variant_x * transform.sine + y * transform.cosine),
                )
            )
        varied.append(replace(stroke, points=points))
    result = replace(document, strokes=varied, metadata=dict(document.metadata))
    result.metadata["variation_seed"] = config.seed
    result.metadata["glyph_variants"] = {
        str(index): variation.glyph_variant
        for index, variation in sorted(context.glyphs.items())
    }
    if started is not None:
        hotspots.record(
            "handwriting.variation_transform",
            (time.perf_counter() - started) * 1000.0,
        )
    return result


def export_handwriting_debug(document: PathDocument, output: Path) -> None:
    candidates = document.metadata.get("connection_debug", [])
    if not isinstance(candidates, list):
        candidates = []
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {document.page_width_mm} {document.page_height_mm}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g id="strokes" fill="none" stroke="black" stroke-width="0.2">',
    ]
    for stroke in document.strokes:
        points = " ".join(f"{point.x},{point.y}" for point in stroke.points)
        color = "#d22" if stroke.char and len(stroke.char) > 1 else "#111"
        lines.append(f'<polyline points="{points}" stroke="{color}"/>')
    lines.append('</g><g id="candidate-curves" fill="none" stroke-width="0.16">')
    for candidate in candidates:
        curve = candidate.get("curve", [])
        if not curve:
            continue
        points = " ".join(f"{point[0]},{point[1]}" for point in curve)
        color = "#0a0" if candidate.get("accepted") else "#d22"
        dash = "" if candidate.get("accepted") else ' stroke-dasharray="0.6 0.4"'
        lines.append(f'<polyline points="{points}" stroke="{color}"{dash}/>')
    lines.append('</g><g id="entry-exit" stroke="none">')
    for candidate in candidates:
        left = candidate.get("left_exit")
        right = candidate.get("right_entry")
        if left:
            lines.append(f'<circle cx="{left[0]}" cy="{left[1]}" r="0.35" fill="#06c"/>')
        if right:
            lines.append(f'<circle cx="{right[0]}" cy="{right[1]}" r="0.35" fill="#090"/>')
    lines.append('</g><g id="collisions" fill="#f0f">')
    for candidate in candidates:
        for point in candidate.get("collision_points", []):
            lines.append(f'<circle cx="{point[0]}" cy="{point[1]}" r="0.28"/>')
    lines.append(
        '</g><g id="travel" fill="none" stroke="#999" stroke-width="0.1" '
        'stroke-dasharray="0.5 0.5">'
    )
    for left, right in pairwise(document.strokes):
        lines.append(
            f'<line x1="{left.points[-1].x}" y1="{left.points[-1].y}" '
            f'x2="{right.points[0].x}" y2="{right.points[0].y}"/>'
        )
    lines.append("</g></svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output.with_suffix(".json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_joining_config(
    root: Mapping[str, object], *, enabled: bool | None = None, mode: str | None = None
) -> JoiningConfig:
    values = root.get("connections")
    if not isinstance(values, Mapping):
        handwriting = _mapping(root, "handwriting")
        values = _mapping(handwriting, "joining")
        warnings.warn(
            "handwriting.joining is deprecated; use the canonical connections section",
            UserWarning,
            stacklevel=2,
        )
    configured = _boolean(values, "enabled")
    selected_mode = mode or str(values.get("mode", "safe"))
    if selected_mode not in {"off", "safe", "aggressive"}:
        raise ValueError("connections.mode must be off, safe or aggressive")
    distance = float(values.get("max_distance_mm", values.get("max_join_gap_mm", 1.5)))
    angle = float(values.get("max_tangent_mismatch_deg", values.get("max_join_angle_deg", 55)))
    vertical = float(values.get("max_vertical_offset_mm", 1.2))
    if selected_mode == "aggressive":
        distance *= 1.5
        angle = max(angle, 85.0)
        vertical *= 1.5
    return JoiningConfig(
        (configured if enabled is None else enabled) and selected_mode != "off",
        distance,
        angle,
        _positive(values, "connector_step_mm"),
        frozenset(values.get("do_not_join_before", [".", ",", "!", "?", ":", ";", ")"])),
        frozenset(values.get("do_not_join_after", ["(", "«", "-"])),
        bool(values.get("lift_between_words", True)),
        selected_mode,
        vertical,
        bool(values.get("connect_letters_only", True)),
        _ratio(values, "min_corridor_inside_ratio", 0.75),
        bool(values.get("allow_connector_outside_ink", True)),
        _nonnegative_default(values, "outside_ink_margin_mm", 0.35),
        _positive_default(values, "contact_epsilon_mm", 0.08),
        _positive_default(values, "collision_clearance_mm", 0.10),
    )


def route_words(
    document: PathDocument,
    glyphs: list[PositionedGlyph],
    config: JoiningConfig,
    *,
    collect_debug: bool = False,
    hotspots: HotspotTimings | None = None,
) -> tuple[PathDocument, dict[str, object]]:
    before = len(document.strokes)
    if not config.enabled:
        words = _words(glyphs)
        pairs = sum(max(0, len(word) - 1) for word in words)
        metrics = _metrics(len(words), pairs, 0, before, before, 0.0, [], pairs)
        metrics.update(
            {
                "enabled": False,
                "mode": "off",
                "eligible_pairs": 0,
                "rejections_by_reason": {"mode_off": pairs},
            }
        )
        metrics.update(_required_metrics(pairs, 0, pairs, 0, 0.0, {"mode_off": pairs}))
        metrics.update(
            {
                "cheap_rejected_pairs": pairs,
                "solver_calls": 0,
                "beziers_built": 0,
                "collision_queries": 0,
                "segments_tested": 0,
            }
        )
        return document, metrics
    by_glyph: dict[int, list[PlotterStroke]] = {}
    for stroke in document.strokes:
        if stroke.glyph_index is not None:
            by_glyph.setdefault(stroke.glyph_index, []).append(stroke)
    words = _words(glyphs)
    if hotspots is None:
        obstacle_index = _SegmentObstacleIndex.build(document.strokes)
    else:
        with hotspots.measure("connections.obstacle_index"):
            obstacle_index = _SegmentObstacleIndex.build(document.strokes)
    counters = _ConnectionCounters()
    output: list[PlotterStroke] = []
    candidates = created = rejected = snapped = 0
    connector_length = 0.0
    gaps: list[float] = []
    rejection_reasons: dict[str, int] = {}
    connection_id = 0
    per_word: list[dict[str, object]] = []
    debug_candidates: list[dict[str, object]] = []
    for word in words:
        word_created = 0
        word_rejected: list[str] = []
        secondary: list[PlotterStroke] = []
        routes: list[_GlyphRoute] = []
        for glyph in word:
            strokes = by_glyph.get(glyph.glyph_index, [])
            if hotspots is None:
                classified = classify_strokes(strokes, glyph.baseline_y_mm)
            else:
                with hotspots.measure("connections.stroke_classification"):
                    classified = classify_strokes(strokes, glyph.baseline_y_mm)
            main = classified.main if classified.confidence >= 0.35 else None
            if main is not None:
                if hotspots is None:
                    routed, anchors = _orient_for_anchors(main, glyph)
                else:
                    with hotspots.measure("connections.anchor_routing"):
                        routed, anchors = _orient_for_anchors(main, glyph)
                routes.append(
                    _GlyphRoute(
                        glyph,
                        routed,
                        anchors[0] if anchors else None,
                        anchors[1] if anchors else None,
                    )
                )
            else:
                routes.append(_GlyphRoute(glyph, None, None, None))
            secondary.extend(stroke for stroke in strokes if stroke is not main)
        combined = (
            replace(routes[0].main, points=list(routes[0].main.points))
            if routes and routes[0].main
            else None
        )
        if routes:
            for left_route, right_route in pairwise(routes):
                candidates += 1
                right = right_route.main
                if (
                    combined is None
                    or left_route.main is None
                    or right is None
                    or left_route.exit is None
                    or right_route.entry is None
                ):
                    reason = "missing_main_stroke"
                    counters.cheap_rejected_pairs += 1
                    if combined is not None:
                        output.append(combined)
                    combined = replace(right, points=list(right.points)) if right else None
                    rejected += 1
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    word_rejected.append(reason)
                    continue
                cheap_candidate = (
                    None
                    if collect_debug
                    else _cheap_connection_rejection(
                        left_route, right_route, config
                    )
                )
                if cheap_candidate is not None:
                    counters.cheap_rejected_pairs += 1
                    candidate = cheap_candidate
                    connector, collision_points, snap_point = [], [], None
                elif hotspots is None:
                    candidate, connector, collision_points, snap_point = (
                        _connection_candidate(
                            left_route,
                            right_route,
                            config,
                            obstacle_index,
                            counters,
                            collect_debug=collect_debug,
                        )
                    )
                else:
                    with hotspots.measure("connections.candidate_solver"):
                        candidate, connector, collision_points, snap_point = (
                            _connection_candidate(
                                left_route,
                                right_route,
                                config,
                                obstacle_index,
                                counters,
                                collect_debug=collect_debug,
                            )
                        )
                reason = candidate.rejection_reason
                if collect_debug:
                    debug_candidates.append(
                        _debug_candidate(
                            left_route,
                            right_route,
                            candidate,
                            connector,
                            collision_points,
                            snap_point,
                        )
                    )
                if not candidate.accepted:
                    output.append(combined)
                    combined = replace(right, points=list(right.points))
                    rejected += 1
                    rejection_reasons[reason or "unknown"] = (
                        rejection_reasons.get(reason or "unknown", 0) + 1
                    )
                    word_rejected.append(reason or "unknown")
                    continue
                gap = candidate.distance_mm
                right_points = list(right.points)
                if snap_point is not None:
                    combined.points[-1] = snap_point
                    right_points[0] = snap_point
                    combined.points.extend(right_points[1:])
                    snapped += 1
                    segment_kind = "snap"
                else:
                    combined.points.extend(_dedupe_boundary(combined.points[-1], connector[1:]))
                    combined.points.extend(_dedupe_boundary(combined.points[-1], right_points[1:]))
                    connector_length += sum(_distance(a, b) for a, b in pairwise(connector))
                    segment_kind = "connector"
                combined.char = f"{combined.char or ''}{right.char or ''}"
                combined.source_glyph_indices = (
                    combined.source_glyph_indices + right.source_glyph_indices
                )
                combined.source_chars += right.source_chars or right.char or ""
                combined.segment_types += (segment_kind,) + right.segment_types
                combined.connection_ids += (connection_id,)
                connection_id += 1
                gaps.append(gap)
                created += 1
                word_created += 1
            if combined is not None:
                output.append(combined)
        output.extend(secondary)
        per_word.append(
            {
                "text": "".join(glyph.char for glyph in word),
                "line_index": word[0].line_index if word else 0,
                "glyph_count": len(word),
                "connections": word_created,
                "remaining_internal_lifts": max(0, len(word) - 1 - word_created),
                "secondary_strokes": len(secondary),
                "rejected_pairs": word_rejected,
            }
        )
    output.extend(stroke for stroke in document.strokes if stroke.glyph_index is None)
    for index, stroke in enumerate(output):
        stroke.id = index
    result = replace(document, strokes=output, metadata=dict(document.metadata))
    result.metadata["word_joining"] = True
    if collect_debug:
        result.metadata["connection_debug"] = debug_candidates
    else:
        result.metadata.pop("connection_debug", None)
    metrics = _metrics(
        len(words), candidates, created, before, len(output), connector_length, gaps, rejected,
        rejection_reasons,
        per_word,
    )
    metrics["mode"] = config.mode
    metrics.update(
        _required_metrics(
            candidates, created, rejected, snapped, connector_length, rejection_reasons
        )
    )
    metrics.update(
        {
            "cheap_rejected_pairs": counters.cheap_rejected_pairs,
            "solver_calls": counters.solver_calls,
            "beziers_built": counters.beziers_built,
            "collision_queries": counters.collision_queries,
            "segments_tested": counters.segments_tested,
        }
    )
    return result, metrics


def _words(glyphs: list[PositionedGlyph]) -> list[list[PositionedGlyph]]:
    words: list[list[PositionedGlyph]] = []
    current: list[PositionedGlyph] = []
    previous: PositionedGlyph | None = None
    for glyph in glyphs:
        boundary = previous is not None and (
            glyph.line_index != previous.line_index
            or (
                glyph.word_index >= 0
                and previous.word_index >= 0
                and glyph.word_index != previous.word_index
            )
            or (
                (glyph.word_index < 0 or previous.word_index < 0)
                and glyph.x_mm - (previous.x_mm + previous.advance_mm) > 1e-6
            )
        )
        if boundary and current:
            words.append(current)
            current = []
        current.append(glyph)
        previous = glyph
    if current:
        words.append(current)
    return words


def _orient_for_anchors(
    stroke: PlotterStroke, glyph: PositionedGlyph
) -> tuple[PlotterStroke, tuple[StrokeAnchor, StrokeAnchor] | None]:
    routed = replace(stroke, points=list(stroke.points))
    anchors = entry_exit_anchors(routed, glyph.baseline_y_mm)
    if anchors is not None and anchors[0].point == routed.points[-1]:
        routed.points.reverse()
        anchors = entry_exit_anchors(routed, glyph.baseline_y_mm)
    return routed, anchors


def _connection_candidate(
    left: _GlyphRoute,
    right: _GlyphRoute,
    config: JoiningConfig,
    obstacles: _SegmentObstacleIndex,
    counters: _ConnectionCounters,
    *,
    collect_debug: bool,
) -> tuple[GlyphConnectionCandidate, list[Point], list[Point], Point | None]:
    counters.solver_calls += 1
    assert left.main is not None and right.main is not None
    assert left.exit is not None and right.entry is not None
    start, end = left.exit.point, right.entry.point
    gap = _distance(start, end)
    vertical = abs(end.y - start.y)
    left_angle = math.atan2(left.exit.tangent.y, left.exit.tangent.x)
    right_angle = math.atan2(right.entry.tangent.y, right.entry.tangent.x)
    target = math.atan2(end.y - start.y, end.x - start.x)
    tangent_mismatch = math.degrees(
        max(_angle_diff(left_angle, target), _angle_diff(target, right_angle))
    )
    routeable_anchors = (
        _distance(start, left.main.points[-1]) <= 1e-6
        and _distance(end, right.main.points[0]) <= 1e-6
    )
    reason: str | None = None
    if left.glyph.line_index != right.glyph.line_index:
        reason = "different_line"
    elif left.glyph.char in config.do_not_join_after or right.glyph.char in config.do_not_join_before:
        reason = "punctuation_rule"
    elif config.connect_letters_only and not (
        left.glyph.char.isalpha() and right.glyph.char.isalpha()
    ):
        reason = "not_letters"
    elif not routeable_anchors:
        reason = "anchor_not_routeable"
    elif gap > config.max_join_gap_mm:
        reason = "distance"
    elif vertical > config.max_vertical_offset_mm:
        reason = "vertical_offset"
    elif end.x + 1e-9 < start.x:
        reason = "backward_motion"

    handle = gap / 3
    c1 = Point(start.x + math.cos(left_angle) * handle, start.y + math.sin(left_angle) * handle)
    c2 = Point(end.x - math.cos(right_angle) * handle, end.y - math.sin(right_angle) * handle)
    controls_are_forward = start.x <= c1.x <= c2.x <= end.x
    if (
        reason is None
        and tangent_mismatch > config.max_join_angle_deg
        and controls_are_forward
    ):
        reason = "tangent_mismatch"

    # Existing contact is already valid geometry and must retain the historical snap
    # semantics even when a synthetic connector would fail direction/tangent checks.
    contact = _contact_point(left.main, right.main, config.contact_epsilon_mm)
    if contact is not None:
        candidate = _make_candidate(
            left,
            right,
            gap,
            tangent_mismatch,
            vertical,
            1.0,
            [],
            False,
            None,
            score_override=0.0,
        )
        return candidate, [start, contact, end], [], contact

    if reason is not None:
        counters.cheap_rejected_pairs += 1
        if not collect_debug:
            return (
                _make_candidate(
                    left,
                    right,
                    gap,
                    tangent_mismatch,
                    vertical,
                    1.0,
                    [],
                    False,
                    reason,
                ),
                [],
                [],
                None,
            )

    count = max(2, math.ceil(gap / config.connector_step_mm))
    curve = [_bezier(start, c1, c2, end, index / count) for index in range(count + 1)]
    counters.beziers_built += 1
    backtracking = any(b.x < a.x - 0.15 for a, b in pairwise(curve))
    if reason is None and backtracking:
        reason = "backward_motion"
    elif reason is None and tangent_mismatch > config.max_join_angle_deg:
        reason = "tangent_mismatch"
    if reason is not None and not collect_debug:
        return (
            _make_candidate(
                left,
                right,
                gap,
                tangent_mismatch,
                vertical,
                1.0,
                [],
                backtracking,
                reason,
            ),
            [],
            [],
            None,
        )

    corridor_ratio = _corridor_inside_ratio(
        curve, start, end, config.outside_ink_margin_mm
    )
    collision_points = _collision_points(
        curve,
        obstacles,
        left.main,
        right.main,
        start,
        end,
        config.collision_clearance_mm,
        counters,
    )
    if reason is None and collision_points:
        reason = "collision"
    elif reason is None and corridor_ratio < (
        config.min_corridor_inside_ratio if config.allow_connector_outside_ink else 1.0
    ):
        reason = "corridor"
    candidate = _make_candidate(
        left,
        right,
        gap,
        tangent_mismatch,
        vertical,
        corridor_ratio,
        collision_points,
        backtracking,
        reason,
    )
    return candidate, curve, collision_points, None


def _cheap_connection_rejection(
    left: _GlyphRoute,
    right: _GlyphRoute,
    config: JoiningConfig,
) -> GlyphConnectionCandidate | None:
    """Reject impossible fast-path pairs while preserving contact overrides."""
    assert left.main is not None and right.main is not None
    assert left.exit is not None and right.entry is not None
    start, end = left.exit.point, right.entry.point
    reason: str | None = None
    if left.glyph.line_index != right.glyph.line_index:
        reason = "different_line"
    elif (
        left.glyph.char in config.do_not_join_after
        or right.glyph.char in config.do_not_join_before
    ):
        reason = "punctuation_rule"
    elif config.connect_letters_only and not (
        left.glyph.char.isalpha() and right.glyph.char.isalpha()
    ):
        reason = "not_letters"
    elif (
        _distance(start, left.main.points[-1]) > 1e-6
        or _distance(end, right.main.points[0]) > 1e-6
    ):
        reason = "anchor_not_routeable"
    gap = _distance(start, end)
    vertical = abs(end.y - start.y)
    if reason is None and gap > config.max_join_gap_mm:
        reason = "distance"
    elif reason is None and vertical > config.max_vertical_offset_mm:
        reason = "vertical_offset"
    elif reason is None and end.x + 1e-9 < start.x:
        reason = "backward_motion"
    if reason is None or _terminal_contact_possible(left, right, config.contact_epsilon_mm):
        return None
    left_angle = math.atan2(left.exit.tangent.y, left.exit.tangent.x)
    right_angle = math.atan2(right.entry.tangent.y, right.entry.tangent.x)
    target = math.atan2(end.y - start.y, end.x - start.x)
    tangent_mismatch = math.degrees(
        max(_angle_diff(left_angle, target), _angle_diff(target, right_angle))
    )
    return _make_candidate(
        left,
        right,
        gap,
        tangent_mismatch,
        vertical,
        1.0,
        [],
        False,
        reason,
    )


def _terminal_contact_possible(
    left: _GlyphRoute, right: _GlyphRoute, epsilon: float
) -> bool:
    assert left.main is not None and right.main is not None
    left_bounds = _segment_bounds(left.main.points[-2], left.main.points[-1])
    right_bounds = _segment_bounds(right.main.points[0], right.main.points[1])
    return _bounds_overlap(
        (
            left_bounds[0] - epsilon,
            left_bounds[1] - epsilon,
            left_bounds[2] + epsilon,
            left_bounds[3] + epsilon,
        ),
        right_bounds,
    )


def _make_candidate(
    left: _GlyphRoute,
    right: _GlyphRoute,
    gap: float,
    tangent_mismatch: float,
    vertical: float,
    corridor_ratio: float,
    collision_points: list[Point],
    backtracking: bool,
    reason: str | None,
    *,
    score_override: float | None = None,
) -> GlyphConnectionCandidate:
    assert left.exit is not None and right.entry is not None
    score = (
        gap
        + vertical * 0.75
        + tangent_mismatch / 45.0
        + (1.0 - corridor_ratio) * 10.0
        + len(collision_points) * 100.0
        + (100.0 if backtracking else 0.0)
    )
    if score_override is not None:
        score = score_override
    return GlyphConnectionCandidate(
        left.glyph.glyph_index,
        right.glyph.glyph_index,
        left.exit,
        right.entry,
        gap,
        tangent_mismatch,
        vertical,
        corridor_ratio,
        len(collision_points),
        score,
        reason is None,
        reason,
    )


def _contact_point(
    left: PlotterStroke, right: PlotterStroke, epsilon: float
) -> Point | None:
    if _distance(left.points[-1], right.points[0]) <= epsilon:
        return Point(
            (left.points[-1].x + right.points[0].x) / 2,
            (left.points[-1].y + right.points[0].y) / 2,
        )
    return _segment_intersection(
        left.points[-2], left.points[-1], right.points[0], right.points[1]
    )


def _segment_intersection(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    denominator = (a.x - b.x) * (c.y - d.y) - (a.y - b.y) * (c.x - d.x)
    if abs(denominator) <= 1e-12:
        return None
    first = a.x * b.y - a.y * b.x
    second = c.x * d.y - c.y * d.x
    point = Point(
        (first * (c.x - d.x) - (a.x - b.x) * second) / denominator,
        (first * (c.y - d.y) - (a.y - b.y) * second) / denominator,
    )
    if _point_on_segment(point, a, b) and _point_on_segment(point, c, d):
        return point
    return None


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    epsilon = 1e-9
    return (
        min(start.x, end.x) - epsilon <= point.x <= max(start.x, end.x) + epsilon
        and min(start.y, end.y) - epsilon <= point.y <= max(start.y, end.y) + epsilon
    )


def _corridor_inside_ratio(
    curve: list[Point], start: Point, end: Point, margin: float
) -> float:
    if not curve:
        return 0.0
    radius = max(margin, 1e-6)
    inside = sum(_point_segment_distance(point, start, end) <= radius for point in curve)
    return inside / len(curve)


def _collision_points(
    curve: list[Point],
    obstacles: _SegmentObstacleIndex,
    left: PlotterStroke,
    right: PlotterStroke,
    start: Point,
    end: Point,
    clearance: float,
    counters: _ConnectionCounters,
) -> list[Point]:
    counters.collision_queries += 1
    collisions: list[Point] = []
    boundary_ignore = max(clearance * 4, 0.35)
    for point in curve[1:-1]:
        point_bounds = (
            point.x - clearance,
            point.y - clearance,
            point.x + clearance,
            point.y + clearance,
        )
        for segment in obstacles.query(point_bounds):
            counters.segments_tested += 1
            stroke, first, second = segment.stroke, segment.first, segment.second
            if not (
                segment.bounds[0] - clearance
                <= point.x
                <= segment.bounds[2] + clearance
                and segment.bounds[1] - clearance
                <= point.y
                <= segment.bounds[3] + clearance
            ):
                continue
            if stroke.id == left.id and min(
                _distance(first, start), _distance(second, start)
            ) <= boundary_ignore:
                continue
            if stroke.id == right.id and min(
                _distance(first, end), _distance(second, end)
            ) <= boundary_ignore:
                continue
            if _point_segment_distance(point, first, second) <= clearance:
                collisions.append(point)
                break
    return _dedupe_points(collisions, clearance)


def _stroke_bounds(stroke: PlotterStroke) -> tuple[float, float, float, float]:
    first = stroke.points[0]
    min_x = max_x = first.x
    min_y = max_y = first.y
    for point in stroke.points[1:]:
        if point.x < min_x:
            min_x = point.x
        elif point.x > max_x:
            max_x = point.x
        if point.y < min_y:
            min_y = point.y
        elif point.y > max_y:
            max_y = point.y
    return min_x, min_y, max_x, max_y


def _segment_bounds(first: Point, second: Point) -> tuple[float, float, float, float]:
    min_x, max_x = first.x, second.x
    min_y, max_y = first.y, second.y
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y
    return min_x, min_y, max_x, max_y


def _segment_obstacle(
    stroke: PlotterStroke,
    segment_index: int,
    first: Point,
    second: Point,
) -> _SegmentObstacle:
    return _SegmentObstacle(
        stroke,
        segment_index,
        first,
        second,
        _segment_bounds(first, second),
    )


def _bounds_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end.x - start.x, end.y - start.y
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-18:
        return _distance(point, start)
    position = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_squared
    position = min(1.0, max(0.0, position))
    projection = Point(start.x + position * dx, start.y + position * dy)
    return _distance(point, projection)


def _dedupe_points(points: list[Point], epsilon: float) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or _distance(result[-1], point) > epsilon:
            result.append(point)
    return result


def _dedupe_boundary(boundary: Point, points: list[Point]) -> list[Point]:
    index = 0
    while index < len(points) and _distance(boundary, points[index]) <= 1e-9:
        index += 1
    return points[index:]


def _bezier(a: Point, b: Point, c: Point, d: Point, t: float) -> Point:
    u = 1 - t
    return Point(
        u**3 * a.x + 3 * u * u * t * b.x + 3 * u * t * t * c.x + t**3 * d.x,
        u**3 * a.y + 3 * u * u * t * b.y + 3 * u * t * t * c.y + t**3 * d.y,
    )


def _metrics(
    words: int,
    candidates: int,
    created: int,
    before: int,
    after: int,
    length: float,
    gaps: list[float],
    rejected: int = 0,
    rejection_reasons: dict[str, int] | None = None,
    per_word: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "enabled": bool(words),
        "mode": "safe" if words else "off",
        "words": words,
        "letter_pairs_total": candidates,
        "eligible_pairs": candidates,
        "connected_pairs": created,
        "rejected_pairs": rejected,
        "join_candidates": candidates,
        "joins_created": created,
        "joins_rejected": rejected,
        "pen_lifts_before_word_routing": before,
        "pen_lifts_after_word_routing": after,
        "pen_lifts_saved_between_glyphs": before - after,
        "pen_lifts_inside_words_before": candidates,
        "pen_lifts_inside_words_after": max(0, candidates - created),
        "pen_lifts_saved": created,
        "connector_draw_length_mm": round(length, 6),
        "average_join_gap_mm": round(sum(gaps) / len(gaps), 6) if gaps else 0.0,
        "rejections_by_reason": rejection_reasons or {},
        "per_word": per_word or [],
    }


def _required_metrics(
    pairs: int,
    accepted: int,
    rejected: int,
    snapped: int,
    connector_length: float,
    reasons: dict[str, int],
) -> dict[str, object]:
    return {
        "pairs_total": pairs,
        "accepted": accepted,
        "rejected": rejected,
        "rejected_distance": reasons.get("distance", 0),
        "rejected_tangent": reasons.get("tangent_mismatch", 0),
        "rejected_collision": reasons.get("collision", 0),
        "rejected_corridor": reasons.get("corridor", 0),
        "snapped_existing_contact": snapped,
        "connector_length_mm": round(connector_length, 6),
    }


def _debug_candidate(
    left: _GlyphRoute,
    right: _GlyphRoute,
    candidate: GlyphConnectionCandidate,
    curve: list[Point],
    collision_points: list[Point],
    snap_point: Point | None,
) -> dict[str, object]:
    return {
        "left": left.glyph.char,
        "right": right.glyph.char,
        "left_glyph_index": candidate.left_glyph_index,
        "right_glyph_index": candidate.right_glyph_index,
        "accepted": candidate.accepted,
        "reason": candidate.rejection_reason,
        "distance_mm": round(candidate.distance_mm, 6),
        "vertical_offset_mm": round(candidate.vertical_offset_mm, 6),
        "tangent_mismatch_deg": round(candidate.tangent_mismatch_deg, 6),
        "corridor_inside_ratio": round(candidate.corridor_inside_ratio, 6),
        "collision_count": candidate.collision_count,
        "score": round(candidate.score, 6),
        "snapped_existing_contact": snap_point is not None,
        "left_exit": [candidate.left_exit.point.x, candidate.left_exit.point.y],
        "right_entry": [candidate.right_entry.point.x, candidate.right_entry.point.y],
        "curve": [[point.x, point.y] for point in curve],
        "collision_points": [[point.x, point.y] for point in collision_points],
    }


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing handwriting mapping: {key}")
    return value


def _positive(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Invalid handwriting value: {key}")
    return float(value)

def _nonnegative(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Invalid handwriting value: {key}")
    return float(value)


def _boolean(values: Mapping[str, object], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Invalid handwriting boolean: {key}")
    return value


def _positive_default(values: Mapping[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Invalid handwriting value: {key}")
    return float(value)


def _nonnegative_default(values: Mapping[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Invalid handwriting value: {key}")
    return float(value)


def _ratio(values: Mapping[str, object], key: str, default: float) -> float:
    value = values.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
    ):
        raise ValueError(f"Invalid handwriting ratio: {key}")
    return float(value)
