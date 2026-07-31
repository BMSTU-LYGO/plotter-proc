from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

from plotter_processor.models import PathDocument, PlotterStroke, Point, PositionedGlyph


@dataclass(frozen=True, slots=True)
class JoiningConfig:
    enabled: bool
    max_join_gap_mm: float
    max_join_angle_deg: float
    connector_step_mm: float
    do_not_join_before: frozenset[str]
    do_not_join_after: frozenset[str]
    lift_between_words: bool


@dataclass(frozen=True, slots=True)
class VariationConfig:
    enabled: bool
    seed: int
    baseline_jitter_mm: float
    rotation_deg: float
    scale_percent: float
    spacing_jitter_mm: float


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


def apply_variation(
    document: PathDocument, glyphs: list[PositionedGlyph], config: VariationConfig
) -> PathDocument:
    if not config.enabled:
        return document
    positions = {glyph.glyph_index: glyph for glyph in glyphs}
    varied: list[PlotterStroke] = []
    parameters: dict[int, tuple[float, float, float, float]] = {}
    for stroke in document.strokes:
        index = stroke.glyph_index
        glyph = positions.get(index) if index is not None else None
        if glyph is None:
            varied.append(stroke)
            continue
        if index not in parameters:
            rng = random.Random(config.seed * 1_000_003 + index)
            parameters[index] = (
                rng.uniform(-config.baseline_jitter_mm, config.baseline_jitter_mm),
                math.radians(rng.uniform(-config.rotation_deg, config.rotation_deg)),
                1 + rng.uniform(-config.scale_percent, config.scale_percent) / 100,
                rng.uniform(-config.spacing_jitter_mm, config.spacing_jitter_mm),
            )
        dy, angle, scale, dx = parameters[index]
        cosine, sine = math.cos(angle), math.sin(angle)
        points = []
        for point in stroke.points:
            x, y = point.x - glyph.x_mm, point.y - glyph.baseline_y_mm
            points.append(
                Point(
                    glyph.x_mm + dx + scale * (x * cosine - y * sine),
                    glyph.baseline_y_mm + dy + scale * (x * sine + y * cosine),
                )
            )
        varied.append(replace(stroke, points=points))
    result = replace(document, strokes=varied, metadata=dict(document.metadata))
    result.metadata["variation_seed"] = config.seed
    return result


def export_handwriting_debug(document: PathDocument, output: Path) -> None:
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {document.page_width_mm} {document.page_height_mm}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g id="strokes" fill="none" stroke="black" stroke-width="0.2">',
    ]
    for stroke in document.strokes:
        points = " ".join(f"{point.x},{point.y}" for point in stroke.points)
        color = "#d22" if stroke.char and len(stroke.char) > 1 else "#111"
        lines.append(f'<polyline points="{points}" stroke="{color}"/>')
    lines.append('</g><g id="entry-exit" fill="#06c">')
    for stroke in document.strokes:
        lines.append(f'<circle cx="{stroke.points[0].x}" cy="{stroke.points[0].y}" r="0.35"/>')
        lines.append(
            f'<circle cx="{stroke.points[-1].x}" cy="{stroke.points[-1].y}" r="0.35" fill="#090"/>'
        )
    lines.append(
        '</g><g id="travel" fill="none" stroke="#999" stroke-width="0.1" stroke-dasharray="0.5 0.5">'
    )
    for left, right in pairwise(document.strokes):
        lines.append(
            f'<line x1="{left.points[-1].x}" y1="{left.points[-1].y}" x2="{right.points[0].x}" y2="{right.points[0].y}"/>'
        )
    lines.append("</g></svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_joining_config(
    root: Mapping[str, object], *, enabled: bool | None = None
) -> JoiningConfig:
    handwriting = _mapping(root, "handwriting")
    values = _mapping(handwriting, "joining")
    configured = _boolean(values, "enabled")
    return JoiningConfig(
        configured if enabled is None else enabled,
        _positive(values, "max_join_gap_mm"),
        _positive(values, "max_join_angle_deg"),
        _positive(values, "connector_step_mm"),
        frozenset(_strings(values, "do_not_join_before")),
        frozenset(_strings(values, "do_not_join_after")),
        _boolean(values, "lift_between_words"),
    )


def route_words(
    document: PathDocument,
    glyphs: list[PositionedGlyph],
    config: JoiningConfig,
) -> tuple[PathDocument, dict[str, object]]:
    before = len(document.strokes)
    if not config.enabled:
        return document, _metrics(0, 0, 0, before, before, 0.0, [])
    positioned = {glyph.glyph_index: glyph for glyph in glyphs}
    by_glyph: dict[int, list[PlotterStroke]] = {}
    for stroke in document.strokes:
        if stroke.glyph_index is not None:
            by_glyph.setdefault(stroke.glyph_index, []).append(stroke)
    words = _words(glyphs)
    output: list[PlotterStroke] = []
    candidates = created = rejected = 0
    connector_length = 0.0
    gaps: list[float] = []
    for word in words:
        mains: list[PlotterStroke] = []
        secondary: list[PlotterStroke] = []
        for glyph in word:
            strokes = by_glyph.get(glyph.glyph_index, [])
            open_strokes = [stroke for stroke in strokes if not stroke.closed]
            main = max(open_strokes, key=_stroke_length, default=None)
            if main is not None:
                mains.append(replace(main, points=list(main.points)))
            secondary.extend(stroke for stroke in strokes if stroke is not main)
        oriented = _orient_word(mains)
        if oriented:
            combined = replace(oriented[0], points=list(oriented[0].points))
            for right in oriented[1:]:
                candidates += 1
                left_glyph = (
                    positioned.get(combined.glyph_index)
                    if combined.glyph_index is not None
                    else None
                )
                right_glyph = (
                    positioned.get(right.glyph_index) if right.glyph_index is not None else None
                )
                connector = _connector(
                    combined.points, right.points, config, left_glyph, right_glyph
                )
                if connector is None:
                    output.append(combined)
                    combined = replace(right, points=list(right.points))
                    rejected += 1
                    continue
                gap = _distance(combined.points[-1], right.points[0])
                combined.points.extend(connector[1:])
                combined.points.extend(right.points[1:])
                combined.char = f"{combined.char or ''}{right.char or ''}"
                connector_length += sum(_distance(a, b) for a, b in pairwise(connector))
                gaps.append(gap)
                created += 1
            output.append(combined)
        output.extend(secondary)
    output.extend(stroke for stroke in document.strokes if stroke.glyph_index is None)
    for index, stroke in enumerate(output):
        stroke.id = index
    result = replace(document, strokes=output, metadata=dict(document.metadata))
    result.metadata["word_joining"] = True
    return result, _metrics(
        len(words), candidates, created, before, len(output), connector_length, gaps, rejected
    )


def _words(glyphs: list[PositionedGlyph]) -> list[list[PositionedGlyph]]:
    words: list[list[PositionedGlyph]] = []
    current: list[PositionedGlyph] = []
    previous: PositionedGlyph | None = None
    for glyph in glyphs:
        boundary = previous is not None and (
            glyph.line_index != previous.line_index
            or glyph.x_mm - (previous.x_mm + previous.advance_mm) > 1e-6
        )
        if boundary and current:
            words.append(current)
            current = []
        current.append(glyph)
        previous = glyph
    if current:
        words.append(current)
    return words


def _orient_word(strokes: list[PlotterStroke]) -> list[PlotterStroke]:
    if not strokes:
        return []
    costs = [(0.0, 0.0)]
    parents: list[tuple[int, int]] = []
    for index in range(1, len(strokes)):
        row = []
        parent = []
        for direction in (0, 1):
            start = strokes[index].points[-1 if direction else 0]
            options = [
                costs[-1][prior] + _distance(strokes[index - 1].points[0 if prior else -1], start)
                for prior in (0, 1)
            ]
            chosen = min(range(2), key=lambda prior: (options[prior], prior))
            row.append(options[chosen])
            parent.append(chosen)
        costs.append((row[0], row[1]))
        parents.append((parent[0], parent[1]))
    direction = min(range(2), key=lambda item: (costs[-1][item], item))
    directions = [direction]
    for parent in reversed(parents):
        direction = parent[direction]
        directions.append(direction)
    directions.reverse()
    return [
        replace(stroke, points=list(reversed(stroke.points)) if direction else list(stroke.points))
        for stroke, direction in zip(strokes, directions)
    ]


def _connector(
    left: list[Point],
    right: list[Point],
    config: JoiningConfig,
    left_glyph: PositionedGlyph | None,
    right_glyph: PositionedGlyph | None,
) -> list[Point] | None:
    if not left_glyph or not right_glyph or left_glyph.line_index != right_glyph.line_index:
        return None
    if left_glyph.char in config.do_not_join_after or right_glyph.char in config.do_not_join_before:
        return None
    start, end = left[-1], right[0]
    gap = _distance(start, end)
    if gap > config.max_join_gap_mm:
        return None
    left_angle = math.atan2(start.y - left[-2].y, start.x - left[-2].x)
    right_angle = math.atan2(right[1].y - end.y, right[1].x - end.x)
    target = math.atan2(end.y - start.y, end.x - start.x)
    if max(_angle_diff(left_angle, target), _angle_diff(target, right_angle)) > math.radians(
        config.max_join_angle_deg
    ):
        return None
    handle = gap / 3
    c1 = Point(start.x + math.cos(left_angle) * handle, start.y + math.sin(left_angle) * handle)
    c2 = Point(end.x - math.cos(right_angle) * handle, end.y - math.sin(right_angle) * handle)
    count = max(2, math.ceil(gap / config.connector_step_mm))
    return [_bezier(start, c1, c2, end, index / count) for index in range(count + 1)]


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
) -> dict[str, object]:
    return {
        "enabled": bool(words),
        "words": words,
        "join_candidates": candidates,
        "joins_created": created,
        "joins_rejected": rejected,
        "pen_lifts_before_word_routing": before,
        "pen_lifts_after_word_routing": after,
        "pen_lifts_saved_between_glyphs": before - after,
        "connector_draw_length_mm": round(length, 6),
        "average_join_gap_mm": round(sum(gaps) / len(gaps), 6) if gaps else 0.0,
    }


def _stroke_length(stroke: PlotterStroke) -> float:
    return sum(_distance(a, b) for a, b in zip(stroke.points, stroke.points[1:]))


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


def _strings(values: Mapping[str, object], key: str) -> list[str]:
    value = values.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"Invalid handwriting list: {key}")
    return value
