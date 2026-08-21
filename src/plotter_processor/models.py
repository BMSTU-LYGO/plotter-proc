from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DocumentText:
    paragraphs: list[str]
    source_path: Path
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
class FontIdentity:
    id: str
    path: Path
    sha256: str


@dataclass(frozen=True, slots=True)
class ShapedGlyph:
    source_characters: str
    glyph_id: int
    glyph_name: str
    font: FontIdentity
    cluster_index: int
    x_advance_font_units: float
    y_advance_font_units: float
    x_offset_font_units: float
    y_offset_font_units: float


@dataclass(frozen=True, slots=True)
class ShapedRun:
    text: str
    glyphs: tuple[ShapedGlyph, ...]
    direction: str
    script: str
    language: str


@dataclass(frozen=True, slots=True)
class TextRun:
    text: str
    direction: str = "ltr"
    script: str = "Cyrl"
    language: str = "ru"


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
    word_index: int = -1
    cluster_index: int = 0
    font_id: str | None = None
    font_sha256: str | None = None
    x_offset_font_units: float = 0.0
    y_offset_font_units: float = 0.0


@dataclass(slots=True)
class LayoutResult:
    glyphs: list[PositionedGlyph]
    warnings: list[str]
    line_count: int
    character_count: int
    used_width_mm: float
    used_height_mm: float


@dataclass(slots=True)
class PlotterStroke:
    id: int
    points: list[Point]
    closed: bool
    glyph_index: int | None = None
    char: str | None = None
    contour_index: int | None = None
    source_glyph_indices: tuple[int, ...] = ()
    source_chars: str = ""
    segment_types: tuple[str, ...] = ()
    word_index: int | None = None
    connection_ids: tuple[int, ...] = ()
    element_id: str | None = None
    element_type: str | None = None
    font_role: str | None = None
    font_sha256: str | None = None
    source_path: str | None = None
    source_page_index: int | None = None
    semantic_role: str | None = None
    layout_group: str | None = None
    preserve_order: bool = False
    z_order: int = 0


@dataclass(slots=True)
class PathDocument:
    page_width_mm: float
    page_height_mm: float
    strokes: list[PlotterStroke]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)
