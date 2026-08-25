from __future__ import annotations

from dataclasses import dataclass, field

from plotter_processor.latex_layout import FormulaInfo
from plotter_processor.layout_models import ExclusionZone, RectMM
from plotter_processor.models import LayoutResult, PlotterStroke, PositionedGlyph
from plotter_processor.schemas import LAYOUT_MODEL_SCHEMA_VERSION


@dataclass(slots=True)
class LayoutPage:
    """A fully positioned page independent from its source parser."""

    page_index: int
    layout: LayoutResult
    graphic_strokes: list[PlotterStroke]
    source_element_ids: tuple[str, ...]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class LayoutModel:
    """Placed document consumed by geometry and handwriting stages."""

    pages: list[LayoutPage]
    warnings: list[str]
    import_statistics: dict[str, object]
    element_details: dict[str, dict[str, object]]
    latex_statistics: dict[str, object] = field(default_factory=dict)
    layout_statistics: dict[str, object] = field(default_factory=dict)
    schema_version: int = LAYOUT_MODEL_SCHEMA_VERSION


@dataclass(slots=True)
class AnchoredPlacement:
    element_id: str
    source_order: int
    target_rect: RectMM
    mapped_rect: RectMM | None
    wrap_mode: str
    anchor_type: str
    warnings: list[str]
    active: bool = False


@dataclass(slots=True)
class PageLayoutState:
    cursor_y: float
    glyphs: list[PositionedGlyph] = field(default_factory=list)
    graphics: list[PlotterStroke] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    text_fragments: list[str] = field(default_factory=list)
    line_count: int = 0
    formulas: list[FormulaInfo] = field(default_factory=list)
    exclusion_zones: list[ExclusionZone] = field(default_factory=list)
    line_boxes: list[RectMM] = field(default_factory=list)
    placements: list[dict[str, object]] = field(default_factory=list)
    table_fragments: list[dict[str, object]] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.glyphs or self.graphics)


# Compatibility names for callers using the pre-UPD_Plotter_14 API.
PageLayout = LayoutPage
PaginatedLayout = LayoutModel
