from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from plotter_processor.models import Point
from plotter_processor.schemas import COMPILED_FONT_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class RasterGlyph:
    char: str
    codepoint: int
    glyph_name: str
    width: int
    height: int
    baseline_x_px: float
    baseline_y_px: float
    pixels_per_font_unit: float
    advance_font_units: int
    grayscale: np.ndarray


@dataclass(frozen=True, slots=True)
class SkeletonNode:
    id: int
    kind: str
    x: float
    y: float
    pixels: tuple[tuple[int, int], ...]
    component_id: int = 0
    crossing_number: int = 0


@dataclass(frozen=True, slots=True)
class SkeletonEdge:
    id: int
    start_node_id: int
    end_node_id: int
    pixels: tuple[tuple[int, int], ...]
    closed: bool
    component_id: int = 0
    length_px: float = 0.0


@dataclass(frozen=True, slots=True)
class RouteEdgeStep:
    edge_id: int
    reversed: bool
    duplicated: bool
    occurrence: int


@dataclass(frozen=True, slots=True)
class ComponentRoute:
    component_id: int
    steps: tuple[RouteEdgeStep, ...]
    start_node_id: int
    end_node_id: int
    closed: bool
    original_length_px: float
    retraced_length_px: float
    retrace_ratio: float


@dataclass(frozen=True, slots=True)
class SmoothedEdge:
    edge_id: int
    start_node_id: int
    end_node_id: int
    component_id: int
    points: tuple[Point, ...]
    length_font_units: float
    closed: bool


@dataclass(frozen=True, slots=True)
class CenterlineStroke:
    id: int
    points: tuple[Point, ...]
    closed: bool
    component_id: int = 0
    retraced_length_font_units: float = 0.0


@dataclass(frozen=True, slots=True)
class CompiledGlyphAnchor:
    point: Point
    stroke_id: int
    point_index: int


@dataclass(frozen=True, slots=True)
class CompiledStrokeMetadata:
    stroke_id: int
    component_id: int
    closed: bool
    retraced_length_font_units: float
    recommended_order: int | None = None
    recommended_direction: str = "auto"


@dataclass(frozen=True, slots=True)
class CenterlineGlyph:
    char: str
    codepoint: int
    glyph_name: str
    advance_font_units: int
    strokes: tuple[CenterlineStroke, ...]
    warnings: tuple[str, ...] = ()
    quality: dict[str, object] = field(default_factory=dict)
    entry_anchor: CompiledGlyphAnchor | None = None
    exit_anchor: CompiledGlyphAnchor | None = None
    stroke_metadata: tuple[CompiledStrokeMetadata, ...] = ()


@dataclass(slots=True)
class CompiledPlotterFont:
    """Normalized runtime font independent from the centerline compiler."""

    font_path: Path
    font_sha256: str
    units_per_em: int
    ascent: int
    descent: int
    line_gap: int
    glyphs: dict[str, CenterlineGlyph]
    warnings: list[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def schema_version(self) -> int:
        return COMPILED_FONT_SCHEMA_VERSION

    @property
    def source_fingerprint(self) -> str:
        return self.font_sha256


CompiledCenterlineFont = CompiledPlotterFont


def compiled_glyph_metadata(
    strokes: tuple[CenterlineStroke, ...],
    *,
    char: str | None = None,
) -> tuple[
    CompiledGlyphAnchor | None,
    CompiledGlyphAnchor | None,
    tuple[CompiledStrokeMetadata, ...],
]:
    points = [
        (point, stroke.id, index)
        for stroke in strokes
        for index, point in enumerate(stroke.points)
    ]
    entry = (
        CompiledGlyphAnchor(*min(points, key=lambda item: (item[0].x, item[0].y)))
        if points
        else None
    )
    exit_anchor = (
        CompiledGlyphAnchor(*max(points, key=lambda item: (item[0].x, -item[0].y)))
        if points
        else None
    )
    order = _recommended_order(char, strokes)
    metadata = tuple(
        CompiledStrokeMetadata(
            stroke.id,
            stroke.component_id,
            stroke.closed,
            stroke.retraced_length_font_units,
            order.get(stroke.id),
            _recommended_direction(stroke) if order else "auto",
        )
        for stroke in strokes
    )
    return entry, exit_anchor, metadata


_HANDWRITING_ORDER_GLYPHS = frozenset("ъьыжфт")


def _recommended_order(
    char: str | None, strokes: tuple[CenterlineStroke, ...]
) -> dict[int, int]:
    if char is None or char.lower() not in _HANDWRITING_ORDER_GLYPHS:
        return {}
    ordered = sorted(
        strokes,
        key=lambda stroke: (
            min((point.x for point in stroke.points), default=0.0),
            -_stroke_length(stroke),
            stroke.id,
        ),
    )
    return {stroke.id: index for index, stroke in enumerate(ordered)}


def _recommended_direction(stroke: CenterlineStroke) -> str:
    if stroke.closed or len(stroke.points) < 2:
        return "auto"
    first, last = stroke.points[0], stroke.points[-1]
    if abs(last.x - first.x) >= abs(last.y - first.y):
        return "forward" if first.x <= last.x else "reverse"
    return "forward" if first.y >= last.y else "reverse"


def _stroke_length(stroke: CenterlineStroke) -> float:
    return sum(
        ((second.x - first.x) ** 2 + (second.y - first.y) ** 2) ** 0.5
        for first, second in zip(stroke.points, stroke.points[1:], strict=False)
    )
