from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from plotter_processor.models import PlotterStroke


@dataclass(frozen=True, slots=True)
class SourceBBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


@dataclass(frozen=True, slots=True)
class SourceTextElement:
    id: str
    source_order: int
    source_page_index: int
    paragraphs: tuple[str, ...]
    bbox: SourceBBox | None = None


@dataclass(frozen=True, slots=True)
class SourceRasterImageElement:
    id: str
    source_order: int
    source_page_index: int
    image_path: Path
    width_px: int
    height_px: int
    displayed_width: float | None
    displayed_height: float | None
    bbox: SourceBBox | None = None


@dataclass(frozen=True, slots=True)
class SourceVectorElement:
    id: str
    source_order: int
    source_page_index: int
    strokes: tuple[PlotterStroke, ...]
    bbox: SourceBBox | None = None


@dataclass(frozen=True, slots=True)
class SourceMathElement:
    id: str
    source_order: int
    source_page_index: int
    expression: str
    display_mode: bool
    source_syntax: str
    bbox: SourceBBox | None = None
    visual_image_path: Path | None = None
    visual_ppmm: float | None = None
    absorbed_element_ids: tuple[str, ...] = ()
    detection_confidence: float | None = None


SourceElement: TypeAlias = (
    SourceTextElement | SourceRasterImageElement | SourceVectorElement | SourceMathElement
)


@dataclass(frozen=True, slots=True)
class SourcePage:
    source_page_index: int
    width_pt: float | None
    height_pt: float | None
    elements: tuple[SourceElement, ...]


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_path: Path
    pages: tuple[SourcePage, ...]
    warnings: tuple[str, ...] = ()

    @property
    def elements(self) -> tuple[SourceElement, ...]:
        return tuple(element for page in self.pages for element in page.elements)
