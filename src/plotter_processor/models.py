from dataclasses import dataclass
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


@dataclass(slots=True)
class Stroke:
    points: list[Point]
    source_component: int


@dataclass(slots=True)
class PathDocument:
    page_width_mm: float
    page_height_mm: float
    strokes: list[Stroke]
    warnings: list[str]

