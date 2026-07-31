from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from plotter_processor.models import Point


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
class CenterlineGlyph:
    char: str
    codepoint: int
    glyph_name: str
    advance_font_units: int
    strokes: tuple[CenterlineStroke, ...]
    warnings: tuple[str, ...] = ()
    quality: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CompiledCenterlineFont:
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
