from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from plotter_processor.models import PlotterStroke


@dataclass(frozen=True, slots=True)
class SourceTextStyle:
    underline: str | None = None
    strike: bool = False
    bold: bool = False
    italic: bool = False
    font_size_pt: float | None = None
    baseline_shift: str | None = None


@dataclass(frozen=True, slots=True)
class SourceTextRun:
    text: str
    style: SourceTextStyle = SourceTextStyle()
    bbox: SourceBBox | None = None


@dataclass(frozen=True, slots=True)
class SourceParagraph:
    runs: tuple[SourceTextRun, ...]
    alignment: str | None = None
    first_line_indent_mm: float | None = None
    hanging_indent_mm: float | None = None
    left_indent_mm: float | None = None
    right_indent_mm: float | None = None
    space_before_mm: float | None = None
    space_after_mm: float | None = None
    line_spacing: float | None = None
    tab_stops_mm: tuple[float, ...] = ()
    style_id: str | None = None
    style_name: str | None = None
    semantic_role: str | None = None
    bbox: SourceBBox | None = None

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)


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

    @property
    def coordinate_unit(self) -> str:
        return "mm"


@dataclass(frozen=True, slots=True)
class SourceTextElement:
    id: str
    source_order: int
    source_page_index: int
    paragraphs: tuple[str, ...]
    bbox: SourceBBox | None = None
    styled_paragraphs: tuple[SourceParagraph, ...] = ()


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
    anchor_type: str = "flow"
    wrap_mode: str = "inline"
    wrap_side: str = "both"
    distance_left_mm: float = 0.0
    distance_right_mm: float = 0.0
    distance_top_mm: float = 0.0
    distance_bottom_mm: float = 0.0
    relative_to_h: str | None = None
    relative_to_v: str | None = None
    behind_text: bool = False
    z_order: int = 0
    rotation_deg: float = 0.0
    anchor_offset_x_mm: float = 0.0
    anchor_offset_y_mm: float = 0.0


@dataclass(frozen=True, slots=True)
class SourceVectorElement:
    id: str
    source_order: int
    source_page_index: int
    strokes: tuple[PlotterStroke, ...]
    bbox: SourceBBox | None = None
    anchor_type: str = "absolute"
    wrap_mode: str = "none"
    wrap_side: str = "both"
    z_order: int = 0


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


@dataclass(frozen=True, slots=True)
class SourcePoint:
    x_mm: float
    y_mm: float


@dataclass(frozen=True, slots=True)
class SourceLineElement:
    id: str
    source_order: int
    source_page_index: int
    start: SourcePoint
    end: SourcePoint
    line_width_mm: float | None = None
    dash_style: str | None = None
    bbox: SourceBBox | None = None
    semantic_role: str = "line"
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class SourceArrowElement:
    id: str
    source_order: int
    source_page_index: int
    points: tuple[SourcePoint, ...]
    head_at_start: bool
    head_at_end: bool
    head_style: str = "open"
    bbox: SourceBBox | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class CellBorders:
    top: bool = True
    right: bool = True
    bottom: bool = True
    left: bool = True


@dataclass(frozen=True, slots=True)
class SourceTableCell:
    row: int
    column: int
    row_span: int
    column_span: int
    paragraphs: tuple[SourceParagraph, ...]
    width_mm: float | None = None
    height_mm: float | None = None
    borders: CellBorders = CellBorders()
    vertical_alignment: str | None = None


@dataclass(frozen=True, slots=True)
class SourceTableElement:
    id: str
    source_order: int
    source_page_index: int
    rows: int
    columns: int
    cells: tuple[SourceTableCell, ...]
    column_widths_mm: tuple[float, ...]
    bbox: SourceBBox | None = None
    repeat_header_rows: int = 0
    source_kind: str = "docx-table"


SourceElement: TypeAlias = (
    SourceTextElement
    | SourceRasterImageElement
    | SourceVectorElement
    | SourceMathElement
    | SourceLineElement
    | SourceArrowElement
    | SourceTableElement
)


@dataclass(frozen=True, slots=True)
class SourcePage:
    source_page_index: int
    width_pt: float | None
    height_pt: float | None
    elements: tuple[SourceElement, ...]

    @property
    def width_mm(self) -> float | None:
        return self.width_pt

    @property
    def height_mm(self) -> float | None:
        return self.height_pt


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_path: Path
    pages: tuple[SourcePage, ...]
    warnings: tuple[str, ...] = ()

    @property
    def elements(self) -> tuple[SourceElement, ...]:
        return tuple(element for page in self.pages for element in page.elements)
