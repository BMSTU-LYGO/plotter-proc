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


@dataclass(frozen=True, slots=True)
class SkeletonEdge:
    id: int
    start_node_id: int
    end_node_id: int
    pixels: tuple[tuple[int, int], ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class CenterlineStroke:
    id: int
    points: tuple[Point, ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class CenterlineGlyph:
    char: str
    codepoint: int
    glyph_name: str
    advance_font_units: int
    strokes: tuple[CenterlineStroke, ...]
    warnings: tuple[str, ...] = ()
    quality: dict[str, float | int | bool] = field(default_factory=dict)


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
