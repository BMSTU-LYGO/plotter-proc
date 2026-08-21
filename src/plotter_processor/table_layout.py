from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from plotter_processor.document_models import SourceTableElement
from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import PlotterStroke, Point, PositionedGlyph
from plotter_processor.paragraph_layout import layout_paragraph
from plotter_processor.text_decorations import build_underlines


@dataclass(slots=True)
class TableFragment:
    glyphs: list[PositionedGlyph]
    strokes: list[PlotterStroke]
    height_mm: float
    rows: tuple[int, ...]
    border_count: int


def table_row_height(size_options: dict[str, object]) -> float:
    return max(8.0, float(size_options["em_size_mm"]) * 1.8)


def layout_table_fragment(
    table: SourceTableElement,
    row_indices: list[int],
    font: LoadedFont,
    *,
    x: float,
    y: float,
    width: float,
    size_options: dict[str, object],
    paragraph_options: Mapping[str, object] | None = None,
) -> TableFragment:
    source_widths = list(table.column_widths_mm)
    if not source_widths or sum(source_widths) <= 0:
        source_widths = [1.0] * table.columns
    scale = width / sum(source_widths)
    columns = [value * scale for value in source_widths]
    row_height = table_row_height(size_options)
    x_edges = [x]
    for value in columns:
        x_edges.append(x_edges[-1] + value)
    y_edges = [y + index * row_height for index in range(len(row_indices) + 1)]
    row_positions = {row: index for index, row in enumerate(row_indices)}
    glyphs: list[PositionedGlyph] = []
    decorations: list[PlotterStroke] = []
    occupied: dict[tuple[int, int], str] = {}
    cells = [cell for cell in table.cells if cell.row in row_positions]
    for cell_index, cell in enumerate(cells):
        local_row = row_positions[cell.row]
        cell_id = f"{cell.row}:{cell.column}"
        for rr in range(cell.row, min(table.rows, cell.row + cell.row_span)):
            if rr not in row_positions:
                continue
            for cc in range(cell.column, min(table.columns, cell.column + cell.column_span)):
                occupied[(row_positions[rr], cc)] = cell_id
        if not any(paragraph.text for paragraph in cell.paragraphs):
            continue
        cell_x = x_edges[cell.column]
        cell_width = sum(columns[cell.column : cell.column + cell.column_span])
        cursor_y = y_edges[local_row] + 0.8
        for paragraph in cell.paragraphs:
            if not paragraph.text:
                continue
            result = layout_paragraph(
                paragraph,
                font,
                content_left_mm=cell_x + 1.2,
                content_right_mm=cell_x + cell_width - 1.2,
                base_size_options=size_options,
                paragraph_options=paragraph_options or {},
            )
            cursor_y += result.space_before_mm
            paragraph_glyphs: list[PositionedGlyph] = []
            for line_index, line in enumerate(result.lines):
                line_scale = float(size_options["em_size_mm"]) / font.metrics.units_per_em
                line_scale *= result.font_scale
                baseline = cursor_y + font.metrics.ascent * line_scale
                for glyph in line.glyphs:
                    positioned = PositionedGlyph(
                        glyph.char, glyph.codepoint, glyph.glyph_name,
                        glyph.x_mm, baseline,
                        glyph.advance_mm, glyph.scale_mm_per_font_unit, line_index,
                        len(glyphs), cell_index, glyph.cluster_index, glyph.font_id,
                        glyph.font_sha256, glyph.x_offset_font_units,
                        glyph.y_offset_font_units,
                    )
                    glyphs.append(positioned)
                    paragraph_glyphs.append(positioned)
                cursor_y += line.advance_mm
            cursor_y += result.space_after_mm
            decorations.extend(build_underlines(
                paragraph,
                paragraph_glyphs,
                element_id=f"{table.id}-cell-{cell.row}-{cell.column}",
                em_size_mm=float(size_options["em_size_mm"]) * result.font_scale,
            ))
    strokes: list[PlotterStroke] = []
    for boundary in range(table.columns + 1):
        active_start: int | None = None
        for row in range(len(row_indices)):
            left_owner = occupied.get((row, boundary - 1)) if boundary else None
            right_owner = occupied.get((row, boundary)) if boundary < table.columns else None
            active = boundary in {0, table.columns} or left_owner != right_owner
            if active and active_start is None:
                active_start = row
            if (not active or row == len(row_indices) - 1) and active_start is not None:
                end_row = row + 1 if active else row
                strokes.append(_border(table.id, Point(x_edges[boundary], y_edges[active_start]), Point(x_edges[boundary], y_edges[end_row]), len(strokes)))
                active_start = None
    for boundary in range(len(row_indices) + 1):
        strokes.append(_border(table.id, Point(x, y_edges[boundary]), Point(x + width, y_edges[boundary]), len(strokes)))
    for decoration in decorations:
        decoration.id = len(strokes)
        strokes.append(decoration)
    return TableFragment(glyphs, strokes, row_height * len(row_indices), tuple(row_indices), len(strokes))


def _border(table_id: str, start: Point, end: Point, index: int) -> PlotterStroke:
    return PlotterStroke(
        index, [start, end], False, element_id=table_id, element_type="table-border",
        semantic_role="table-border", segment_types=("table-border",),
        preserve_order=True, z_order=-10,
    )
