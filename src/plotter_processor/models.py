from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class DocumentText:
    paragraphs: list[str]
    source_path: Path
    warnings: list[str]


@dataclass(slots=True)
class RenderedPage:
    width_px: int
    height_px: int
    dpi: int
    image: np.ndarray
    line_boxes: list[tuple[int, int, int, int]]
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PageSpec:
    name: str
    width_mm: float
    height_mm: float


@dataclass(frozen=True, slots=True)
class FontMetrics:
    units_per_em: int
    ascent: int
    descent: int
    line_gap: int


@dataclass(frozen=True, slots=True)
class PositionedGlyph:
    char: str
    codepoint: int
    glyph_name: str
    x_mm: float
    baseline_y_mm: float
    advance_mm: float
    scale_mm_per_font_unit: float
    line_index: int
    glyph_index: int


@dataclass(slots=True)
class LayoutResult:
    glyphs: list[PositionedGlyph]
    warnings: list[str]
    line_count: int
    character_count: int
    used_width_mm: float
    used_height_mm: float


@dataclass(slots=True)
class Stroke:
    points: list[Point]
    source_component: int


@dataclass(slots=True)
class PlotterStroke:
    id: int
    points: list[Point]
    closed: bool
    glyph_index: int | None = None
    char: str | None = None
    contour_index: int | None = None


@dataclass(slots=True)
class PathDocument:
    page_width_mm: float
    page_height_mm: float
    strokes: list[Stroke] | list[PlotterStroke]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)
