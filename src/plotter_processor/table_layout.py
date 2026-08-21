from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from plotter_processor.document_models import SourceTableCell, SourceTableElement
from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import PlotterStroke, Point, PositionedGlyph
from plotter_processor.paragraph_layout import ParagraphLayout, layout_paragraph
from plotter_processor.text_decorations import build_underlines


@dataclass(frozen=True, slots=True)
class CellLayout:
    cell: SourceTableCell
    paragraphs: tuple[ParagraphLayout, ...]
    required_height_mm: float


@dataclass(frozen=True, slots=True)
class TableLayoutPlan:
    column_widths_mm: tuple[float, ...]
    row_heights_mm: tuple[float, ...]
    cell_layouts: dict[tuple[int, int], CellLayout]
    width_mm: float
    scale: float
    padding_mm: float
    text_scale: float
    warnings: tuple[str, ...]
    auto_height_rows: int


@dataclass(slots=True)
class TableFragment:
    glyphs: list[PositionedGlyph]
    strokes: list[PlotterStroke]
    height_mm: float
    rows: tuple[int, ...]
    border_count: int
    row_heights_mm: tuple[float, ...]
    warnings: tuple[str, ...] = ()


def table_row_height(size_options: dict[str, object]) -> float:
    """Legacy minimum retained for callers; actual rows are measured by the plan."""
    return max(8.0, float(size_options["em_size_mm"]) * 1.8)


def plan_table_layout(
    table: SourceTableElement,
    font: LoadedFont,
    *,
    available_width_mm: float,
    page_scale: float,
    size_options: Mapping[str, object],
    paragraph_options: Mapping[str, object] | None = None,
    table_options: Mapping[str, object] | None = None,
) -> TableLayoutPlan:
    options = dict(table_options or {})
    warnings: list[str] = []
    source_widths = list(table.column_widths_mm)
    valid_widths = (
        len(source_widths) == table.columns
        and all(value > 0 for value in source_widths)
        and sum(source_widths) > 0
    )
    if not valid_widths:
        source_widths = [1.0] * table.columns
        warnings.append("table_column_widths_equal_fallback")
    source_width = table.preferred_width_mm or (
        sum(table.column_widths_mm) if valid_widths else None
    )
    preferred_width = source_width * page_scale if source_width else available_width_mm
    target_width = min(max(0.1, preferred_width), available_width_mm)
    width_scale = target_width / sum(source_widths)
    columns = tuple(value * width_scale for value in source_widths)
    min_column = float(options.get("min_column_width_mm", 8.0))
    if min(columns, default=min_column) < min_column:
        warnings.append("table_columns_below_configured_minimum_controlled_shrink")

    padding_base = float(options.get("cell_padding_mm", 1.2))
    padding = padding_base * page_scale if options.get("scale_padding_with_page", True) else padding_base
    padding = min(
        float(options.get("max_cell_padding_mm", 2.0)),
        max(float(options.get("min_cell_padding_mm", 0.7)), padding),
    )
    min_text_scale = float(options.get("min_text_scale", 0.75))
    narrow_factor = min((value / min_column for value in columns), default=1.0)
    text_scale = min(1.0, max(min_text_scale, narrow_factor))
    scaled_size = dict(size_options)
    scaled_size["em_size_mm"] = float(scaled_size["em_size_mm"]) * text_scale
    minimum_row = table_row_height(scaled_size)
    row_heights = [minimum_row for _ in range(table.rows)]
    for row, source_height in enumerate(table.row_heights_mm):
        if row < len(row_heights) and source_height is not None:
            row_heights[row] = max(row_heights[row], source_height * page_scale)

    x_edges = [0.0]
    for width in columns:
        x_edges.append(x_edges[-1] + width)
    cell_layouts: dict[tuple[int, int], CellLayout] = {}
    required_by_span: list[tuple[SourceTableCell, float]] = []
    for cell in table.cells:
        cell_width = sum(columns[cell.column : cell.column + cell.column_span])
        content_width = cell_width - 2 * padding
        if content_width <= 0:
            warnings.append(f"table_cell_padding_clamped:{cell.row}:{cell.column}")
            content_width = max(0.2, cell_width * 0.5)
        layouts: list[ParagraphLayout] = []
        for paragraph in cell.paragraphs:
            if not paragraph.text:
                continue
            try:
                layout = layout_paragraph(
                    paragraph,
                    font,
                    content_left_mm=padding,
                    content_right_mm=padding + content_width,
                    base_size_options=scaled_size,
                    paragraph_options=paragraph_options or {},
                )
            except ValueError as error:
                if "indents leave no usable" not in str(error):
                    raise
                warnings.append(f"table_cell_indent_clamped:{cell.row}:{cell.column}")
                layout = layout_paragraph(
                    replace(
                        paragraph,
                        first_line_indent_mm=0.0,
                        hanging_indent_mm=0.0,
                        left_indent_mm=0.0,
                        right_indent_mm=0.0,
                    ),
                    font,
                    content_left_mm=padding,
                    content_right_mm=padding + content_width,
                    base_size_options=scaled_size,
                    paragraph_options=paragraph_options or {},
                )
            layouts.append(layout)
        text_height = sum(
            layout.space_before_mm
            + sum(line.advance_mm for line in layout.lines)
            + layout.space_after_mm
            for layout in layouts
        )
        required = max(minimum_row, text_height + 2 * padding)
        cell_layouts[(cell.row, cell.column)] = CellLayout(cell, tuple(layouts), required)
        required_by_span.append((cell, required))
        if cell.row_span == 1:
            row_heights[cell.row] = max(row_heights[cell.row], required)

    for cell, required in required_by_span:
        if cell.row_span <= 1:
            continue
        rows = range(cell.row, min(table.rows, cell.row + cell.row_span))
        current = sum(row_heights[row] for row in rows)
        if current + 1e-9 < required:
            addition = (required - current) / max(1, len(tuple(rows)))
            for row in rows:
                row_heights[row] += addition

    return TableLayoutPlan(
        columns,
        tuple(row_heights),
        cell_layouts,
        sum(columns),
        target_width / source_width if source_width else 1.0,
        padding,
        text_scale,
        tuple(dict.fromkeys(warnings)),
        sum(height > minimum_row + 1e-9 for height in row_heights),
    )


def protected_row_end(table: SourceTableElement, start_row: int) -> int:
    """Return the first row after every merged group touching start_row."""
    end = start_row + 1
    changed = True
    while changed:
        changed = False
        for cell in table.cells:
            cell_end = cell.row + cell.row_span
            if cell.row < end and cell_end > start_row and cell_end > end:
                end = cell_end
                changed = True
    return min(table.rows, end)


def layout_table_fragment(
    table: SourceTableElement,
    row_indices: list[int],
    font: LoadedFont,
    *,
    x: float,
    y: float,
    width: float | None = None,
    size_options: dict[str, object],
    paragraph_options: Mapping[str, object] | None = None,
    table_options: Mapping[str, object] | None = None,
    page_scale: float = 1.0,
    plan: TableLayoutPlan | None = None,
) -> TableFragment:
    plan = plan or plan_table_layout(
        table,
        font,
        available_width_mm=width or sum(table.column_widths_mm),
        page_scale=page_scale,
        size_options=size_options,
        paragraph_options=paragraph_options,
        table_options=table_options,
    )
    columns = plan.column_widths_mm
    x_edges = [x]
    for value in columns:
        x_edges.append(x_edges[-1] + value)
    local_row = {source_row: index for index, source_row in enumerate(row_indices)}
    fragment_heights = tuple(plan.row_heights_mm[row] for row in row_indices)
    y_edges = [y]
    for value in fragment_heights:
        y_edges.append(y_edges[-1] + value)
    glyphs: list[PositionedGlyph] = []
    decorations: list[PlotterStroke] = []
    occupied: dict[tuple[int, int], str] = {}

    for cell_index, cell in enumerate(table.cells):
        if cell.row not in local_row:
            continue
        row_position = local_row[cell.row]
        included_rows = [
            row for row in range(cell.row, min(table.rows, cell.row + cell.row_span))
            if row in local_row
        ]
        if not included_rows:
            continue
        owner = f"{cell.row}:{cell.column}"
        for source_row in included_rows:
            for column in range(cell.column, min(table.columns, cell.column + cell.column_span)):
                occupied[(local_row[source_row], column)] = owner
        prepared = plan.cell_layouts.get((cell.row, cell.column))
        if prepared is None:
            continue
        cell_x = x_edges[cell.column]
        cell_height = sum(plan.row_heights_mm[row] for row in included_rows)
        content_height = max(0.0, prepared.required_height_mm - 2 * plan.padding_mm)
        free = max(0.0, cell_height - 2 * plan.padding_mm - content_height)
        vertical = cell.vertical_alignment or "top"
        shift = free / 2 if vertical == "center" else free if vertical == "bottom" else 0.0
        cursor_y = y_edges[row_position] + plan.padding_mm + shift
        source_paragraphs = [paragraph for paragraph in cell.paragraphs if paragraph.text]
        for paragraph, layout in zip(source_paragraphs, prepared.paragraphs, strict=True):
            cursor_y += layout.space_before_mm
            paragraph_glyphs: list[PositionedGlyph] = []
            for line_index, line in enumerate(layout.lines):
                scale = float(size_options["em_size_mm"]) * plan.text_scale
                scale = scale / font.metrics.units_per_em * layout.font_scale
                baseline = cursor_y + font.metrics.ascent * scale
                for glyph in line.glyphs:
                    positioned = replace(
                        glyph,
                        x_mm=cell_x + glyph.x_mm,
                        baseline_y_mm=baseline,
                        line_index=line_index,
                        glyph_index=len(glyphs),
                        word_index=cell_index,
                    )
                    glyphs.append(positioned)
                    paragraph_glyphs.append(positioned)
                cursor_y += line.advance_mm
            cursor_y += layout.space_after_mm
            decorations.extend(build_underlines(
                paragraph,
                paragraph_glyphs,
                element_id=f"{table.id}-cell-{cell.row}-{cell.column}",
                em_size_mm=float(size_options["em_size_mm"])
                * plan.text_scale
                * layout.font_scale,
            ))

    strokes = _table_borders(table, row_indices, occupied, x_edges, y_edges)
    for decoration in decorations:
        decoration.id = len(strokes)
        strokes.append(decoration)
    return TableFragment(
        glyphs,
        strokes,
        sum(fragment_heights),
        tuple(row_indices),
        len(strokes),
        fragment_heights,
        plan.warnings,
    )


def _table_borders(
    table: SourceTableElement,
    rows: list[int],
    occupied: dict[tuple[int, int], str],
    x_edges: list[float],
    y_edges: list[float],
) -> list[PlotterStroke]:
    segments: list[tuple[Point, Point]] = []
    for boundary in range(table.columns + 1):
        for row in range(len(rows)):
            left_owner = occupied.get((row, boundary - 1)) if boundary else None
            right_owner = occupied.get((row, boundary)) if boundary < table.columns else None
            if boundary in {0, table.columns} or left_owner != right_owner:
                segments.append((
                    Point(x_edges[boundary], y_edges[row]),
                    Point(x_edges[boundary], y_edges[row + 1]),
                ))
    for boundary in range(len(rows) + 1):
        for column in range(table.columns):
            upper_owner = occupied.get((boundary - 1, column)) if boundary else None
            lower_owner = occupied.get((boundary, column)) if boundary < len(rows) else None
            if boundary in {0, len(rows)} or upper_owner != lower_owner:
                segments.append((
                    Point(x_edges[column], y_edges[boundary]),
                    Point(x_edges[column + 1], y_edges[boundary]),
                ))
    return [_border(table.id, start, end, index) for index, (start, end) in enumerate(segments)]


def _border(table_id: str, start: Point, end: Point, index: int) -> PlotterStroke:
    return PlotterStroke(
        index,
        [start, end],
        False,
        element_id=table_id,
        element_type="table-border",
        semantic_role="table-border",
        segment_types=("table-border",),
        preserve_order=True,
        z_order=-10,
    )
