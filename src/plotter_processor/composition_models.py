from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ElementPlacement:
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float | None = None


@dataclass(frozen=True, slots=True)
class DocumentElement:
    id: str
    type: str
    placement: ElementPlacement
    z_order: int = 0
    travel_group: str | None = None
    preserve_stroke_order: bool = True


@dataclass(frozen=True, slots=True)
class TextElement(DocumentElement):
    text: str = ""
    size: str = "normal"
    font_mode: str = "centerline"


@dataclass(frozen=True, slots=True)
class SvgElement(DocumentElement):
    path: Path = Path()
    fit: str = "contain"


@dataclass(frozen=True, slots=True)
class PlotterDocument:
    version: int
    page: str
    primary_font: Path
    fallback_fonts: tuple[tuple[str, Path], ...]
    elements: tuple[DocumentElement, ...]
    source_path: Path
    warnings: tuple[str, ...] = field(default_factory=tuple)
