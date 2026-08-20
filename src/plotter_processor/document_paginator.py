from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from plotter_processor.document_models import (
    SourceArrowElement,
    SourceDocument,
    SourceLineElement,
    SourceMathElement,
    SourceRasterImageElement,
    SourceTableElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.font_loader import LoadedFont
from plotter_processor.image_preprocessor import preprocess_image
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.latex_layout import FormulaInfo, layout_latex_paragraph, layout_math_element
from plotter_processor.latex_parser import contains_latex
from plotter_processor.latex_renderer import math_renderer_from_options, render_visual_math_image
from plotter_processor.layout_debug import export_layout_debug
from plotter_processor.layout_models import (
    ExclusionZone,
    RectMM,
    available_intervals,
    center_displacement,
    choose_widest_interval,
    intersection_area,
    map_source_rect,
    rect_payload,
)
from plotter_processor.models import LayoutResult, PageSpec, PlotterStroke, Point, PositionedGlyph
from plotter_processor.shape_layout import arrow_strokes, line_strokes
from plotter_processor.table_layout import layout_table_fragment, table_row_height
from plotter_processor.text_decorations import build_underlines
from plotter_processor.text_normalizer import normalize_text
from plotter_processor.vector_layout import OVERFLOW_ERROR, layout_text


@dataclass(slots=True)
class PageLayout:
    page_index: int
    layout: LayoutResult
    graphic_strokes: list[PlotterStroke]
    source_element_ids: tuple[str, ...]
    warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PaginatedLayout:
    pages: list[PageLayout]
    warnings: list[str]
    import_statistics: dict[str, object]
    element_details: dict[str, dict[str, object]]
    latex_statistics: dict[str, object] = field(default_factory=dict)
    layout_statistics: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class _PageState:
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


def paginate_document(
    document: SourceDocument,
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    size_options: Mapping[str, object],
    image_options: Mapping[str, object],
    pagination_options: Mapping[str, object],
    *,
    enabled: bool = True,
    image_mode: str = "auto",
    image_debug_dir: Path | None = None,
    latex_mode: str = "off",
    latex_options: Mapping[str, object] | None = None,
    latex_debug_dir: Path | None = None,
    latex_stroke_mode: str | None = None,
    strict_latex_quality: bool | None = None,
    document_layout_mode: str = "reflow",
    document_layout_options: Mapping[str, object] | None = None,
    layout_debug_dir: Path | None = None,
    preserve_source_page_breaks: bool = True,
    tab_spaces: int = 4,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> PaginatedLayout:
    if document_layout_mode not in {"reflow", "hybrid", "preserve"}:
        raise ValueError(f"Unknown document layout mode: {document_layout_mode}")
    left = _number(margins, "left")
    right = _number(margins, "right")
    top = _number(margins, "top")
    bottom_margin = _number(margins, "bottom")
    usable_width = page.width_mm - left - right
    footer = _mapping(pagination_options, "footer")
    footer_reserved = _number(footer, "reserved_height_mm") if footer.get("enabled", True) else 0.0
    content_bottom = page.height_mm - bottom_margin - footer_reserved
    content_rect = RectMM(left, top, usable_width, content_bottom - top)
    if content_bottom <= top:
        raise ValueError("Pagination footer leaves no usable page height")
    em_size = _number(size_options, "em_size_mm")
    scale = em_size / font.metrics.units_per_em
    glyph_height = (font.metrics.ascent - font.metrics.descent) * scale
    line_advance = glyph_height * _number(size_options, "line_height_multiplier")
    paragraph_spacing = _number(size_options, "paragraph_spacing_mm")
    spacing_before = float(image_options.get("spacing_before_mm", 2.0))
    spacing_after = float(image_options.get("spacing_after_mm", 2.0))
    default_width_ratio = float(image_options.get("default_width_ratio", 0.75))
    max_height_ratio = float(image_options.get("max_height_ratio", 0.60))
    pages: list[PageLayout] = []
    state = _PageState(top)
    warnings = list(document.warnings)
    details: dict[str, dict[str, object]] = {}
    image_found = image_vectorized = image_strokes = image_points = vector_count = 0
    underline_count = line_count_semantic = arrow_count = table_count = table_cells = 0
    table_pages: set[tuple[str, int]] = set()
    formula_index = 0
    rendered_formulas: list[FormulaInfo] = []
    placement_records: list[dict[str, object]] = []
    all_line_boxes: list[dict[str, object]] = []
    layout_config = dict(document_layout_options or {})
    preserve_config = dict(_optional_mapping(layout_config, "preserve"))
    hybrid_config = dict(_optional_mapping(layout_config, "hybrid"))
    latex_config = dict(latex_options or {})
    renderer = (
        math_renderer_from_options(
            latex_config,
            stroke_mode=latex_stroke_mode,
            strict_quality=strict_latex_quality,
        )
        if latex_mode in {"auto", "mathtext"}
        else None
    )

    def add_source_id(element_id: str) -> None:
        if element_id not in state.source_ids:
            state.source_ids.append(element_id)

    def finish_page() -> None:
        nonlocal state
        if not state.has_content:
            state.cursor_y = top
            return
        used_width = max(
            (glyph.x_mm + glyph.advance_mm - left for glyph in state.glyphs), default=0.0
        )
        character_count = sum(len(fragment) for fragment in state.text_fragments)
        layout = LayoutResult(
            state.glyphs,
            list(dict.fromkeys(state.warnings)),
            max(1, state.line_count),
            character_count,
            max(0.0, used_width),
            max(0.0, state.cursor_y - top),
        )
        output_page_index = len(pages)
        pages.append(PageLayout(
            output_page_index, layout, state.graphics, tuple(state.source_ids),
            list(dict.fromkeys(state.warnings)),
            {
                "text": "".join(state.text_fragments),
                "formulas": [asdict(formula) for formula in state.formulas],
                "placements": list(state.placements),
                "line_boxes": [rect_payload(box) for box in state.line_boxes],
                "table_fragments": list(state.table_fragments),
            },
        ))
        all_line_boxes.extend(
            {"page_index": output_page_index, "bbox": rect_payload(box)}
            for box in state.line_boxes
        )
        warnings.extend(state.warnings)
        state = _PageState(top)

    def ensure_height(required: float) -> None:
        if state.cursor_y + required <= content_bottom + 1e-9:
            return
        if not enabled:
            raise ValueError(OVERFLOW_ERROR)
        finish_page()
        if state.cursor_y + required > content_bottom + 1e-9:
            raise ValueError("An element is taller than the usable page area")

    for source_page_position, source_page in enumerate(document.pages):
        if source_page_position and preserve_source_page_breaks and state.has_content:
            finish_page()
        preplacements: dict[str, tuple[RectMM, RectMM | None, str, list[str]]] = {}
        if document_layout_mode != "reflow":
            provisional: list[dict[str, object]] = []
            for candidate in source_page.elements:
                if isinstance(candidate, SourceRasterImageElement):
                    if candidate.wrap_mode == "inline" or candidate.anchor_type == "flow":
                        continue
                    if (
                        document_layout_mode == "hybrid"
                        and candidate.relative_to_v not in {"page", "margin"}
                    ):
                        continue
                    candidate_width, candidate_height = _image_size(
                        candidate,
                        usable_width,
                        content_bottom - top,
                        default_width_ratio,
                        max_height_ratio,
                    )
                    candidate_mapped = _mapped_element_rect(
                        candidate.bbox,
                        source_page.width_mm,
                        source_page.height_mm,
                        content_rect,
                        float(preserve_config.get("max_upscale", 1.10)),
                    )
                    candidate_rect, candidate_wrap, candidate_warnings = _place_raster(
                        candidate,
                        document_layout_mode,
                        candidate_mapped,
                        candidate_width,
                        candidate_height,
                        top,
                        content_rect,
                        provisional,
                        hybrid_config,
                        spacing_before,
                    )
                elif isinstance(candidate, SourceVectorElement):
                    candidate_width, candidate_height = _vector_size(
                        candidate, usable_width, content_bottom - top
                    )
                    candidate_mapped = _mapped_element_rect(
                        candidate.bbox,
                        source_page.width_mm,
                        source_page.height_mm,
                        content_rect,
                        float(preserve_config.get("max_upscale", 1.10)),
                    )
                    candidate_rect, candidate_wrap, candidate_warnings = _place_vector(
                        candidate,
                        document_layout_mode,
                        candidate_mapped,
                        candidate_width,
                        candidate_height,
                        top,
                        content_rect,
                        provisional,
                        hybrid_config,
                        spacing_before,
                    )
                else:
                    continue
                preplacements[candidate.id] = (
                    candidate_rect,
                    candidate_mapped,
                    candidate_wrap,
                    candidate_warnings,
                )
                provisional.append({"output_bbox_mm": rect_payload(candidate_rect)})
                zone_wrap = candidate_wrap
                if document_layout_mode == "preserve" and zone_wrap == "none":
                    zone_wrap = "square"
                if zone_wrap in {"square", "top_bottom"}:
                    padding = float(hybrid_config.get("image_padding_mm", 2.0))
                    state.exclusion_zones.append(ExclusionZone(
                        candidate_rect,
                        getattr(candidate, "wrap_side", "both"),
                        candidate.id,
                        padding_left_mm=padding,
                        padding_right_mm=padding,
                    ))
        for element in source_page.elements:
            if isinstance(element, SourceTextElement):
                normalized_paragraphs: list[str] = []
                for raw_paragraph in element.paragraphs:
                    normalized, normalization_warnings = normalize_text(raw_paragraph)
                    warnings.extend(normalization_warnings)
                    normalized_paragraphs.extend(normalized.split("\n"))
                normalized_paragraphs = _merge_multiline_math_blocks(normalized_paragraphs)
                for paragraph_index, paragraph in enumerate(normalized_paragraphs):
                    paragraph_glyph_start = len(state.glyphs)
                    if not paragraph:
                        ensure_height(line_advance)
                        state.cursor_y += line_advance
                        state.text_fragments.append("\n")
                        add_source_id(element.id)
                        continue
                    if renderer is not None and contains_latex(paragraph):
                        if document_layout_mode != "reflow" and state.exclusion_zones:
                            state.cursor_y = _clear_blocking_zones(
                                state.cursor_y, line_advance, state.exclusion_zones
                            )
                        try:
                            rich_lines, formula_index = layout_latex_paragraph(
                                paragraph,
                                font,
                                usable_width,
                                dict(size_options),
                                latex_config,
                                renderer,
                                formula_index_start=formula_index,
                                element_id=element.id,
                                source_page_index=element.source_page_index,
                                debug_dir=latex_debug_dir,
                                tab_spaces=tab_spaces,
                                engine=engine,
                                language=language,
                                script=script,
                                direction=direction,
                                features=features,
                            )
                        except ValueError as error:
                            raise ValueError(
                                f"Source page {element.source_page_index + 1}, "
                                f"source element {element.id!r}: {error}"
                            ) from error
                        if formula_index > int(
                            latex_config.get("max_elements_per_document", 500)
                        ):
                            raise ValueError(
                                "Document exceeds latex.max_elements_per_document "
                                f"({latex_config.get('max_elements_per_document', 500)})"
                            )
                        for rich_line in rich_lines:
                            required = (
                                rich_line.spacing_before_mm
                                + rich_line.advance_mm
                                + rich_line.spacing_after_mm
                            )
                            ensure_height(required)
                            state.cursor_y += rich_line.spacing_before_mm
                            for glyph in rich_line.glyphs:
                                state.glyphs.append(replace(
                                    glyph,
                                    x_mm=left + glyph.x_mm,
                                    baseline_y_mm=state.cursor_y + glyph.baseline_y_mm,
                                    line_index=state.line_count,
                                    glyph_index=len(state.glyphs),
                                ))
                            for stroke in rich_line.formula_strokes:
                                state.graphics.append(replace(
                                    stroke,
                                    id=len(state.graphics),
                                    source_page_index=element.source_page_index,
                                    points=[
                                        Point(left + point.x, state.cursor_y + point.y)
                                        for point in stroke.points
                                    ],
                                ))
                            placed_infos = _place_formula_infos(
                                rich_line.formula_infos, left, state.cursor_y
                            )
                            state.formulas.extend(placed_infos)
                            rendered_formulas.extend(placed_infos)
                            state.warnings.extend(rich_line.warnings)
                            state.cursor_y += rich_line.advance_mm + rich_line.spacing_after_mm
                            state.line_count += 1
                            add_source_id(element.id)
                        state.text_fragments.append(paragraph)
                        if paragraph_index < len(normalized_paragraphs) - 1:
                            state.text_fragments.append("\n")
                        if state.cursor_y + paragraph_spacing <= content_bottom + 1e-9:
                            state.cursor_y += paragraph_spacing
                        continue
                    if document_layout_mode != "reflow" and state.exclusion_zones:
                        _layout_text_around_zones(
                            paragraph,
                            state,
                            font,
                            page,
                            margins,
                            size_options,
                            content_bottom,
                            glyph_height,
                            line_advance,
                            scale,
                            add_source_id,
                            element.id,
                            tab_spaces=tab_spaces,
                            engine=engine,
                            language=language,
                            script=script,
                            direction=direction,
                            features=features,
                        )
                        state.text_fragments.append(paragraph)
                        if paragraph_index < len(normalized_paragraphs) - 1:
                            state.text_fragments.append("\n")
                        if state.cursor_y + paragraph_spacing <= content_bottom + 1e-9:
                            state.cursor_y += paragraph_spacing
                        continue
                    tall_page = PageSpec("flow", page.width_mm, 1_000_000.0)
                    tall_margins = dict(margins)
                    tall_margins["top"] = 0.0
                    tall_margins["bottom"] = 0.0
                    try:
                        flowed = layout_text(
                            [paragraph], font, tall_page, tall_margins, size_options,
                            tab_spaces=tab_spaces, engine=engine, language=language,
                            script=script, direction=direction, features=features,
                        )
                    except ValueError as error:
                        too_wide = next(
                            (
                                character
                                for character in paragraph
                                if _text_width(character, font, scale) > usable_width
                            ),
                            None,
                        )
                        if too_wide is not None:
                            raise ValueError(
                                f'Glyph "{too_wide}" is wider than the usable page width'
                            ) from error
                        raise
                    line_groups: dict[int, list[PositionedGlyph]] = {}
                    for glyph in flowed.glyphs:
                        line_groups.setdefault(glyph.line_index, []).append(glyph)
                    for line_index in range(flowed.line_count):
                        ensure_height(glyph_height)
                        source_line = line_groups.get(line_index, [])
                        baseline = state.cursor_y + font.metrics.ascent * scale
                        global_line = state.line_count
                        for glyph in source_line:
                            state.glyphs.append(replace(
                                glyph,
                                baseline_y_mm=baseline,
                                line_index=global_line,
                                glyph_index=len(state.glyphs),
                            ))
                        state.cursor_y += line_advance
                        state.line_count += 1
                        if source_line:
                            line_left = min(glyph.x_mm for glyph in source_line)
                            line_right = max(
                                glyph.x_mm + glyph.advance_mm for glyph in source_line
                            )
                            state.line_boxes.append(RectMM(
                                line_left,
                                state.cursor_y - line_advance,
                                line_right - line_left,
                                line_advance,
                            ))
                    if paragraph_index < len(element.styled_paragraphs):
                        decorations = build_underlines(
                            element.styled_paragraphs[paragraph_index],
                            state.glyphs[paragraph_glyph_start:],
                            element_id=element.id,
                            em_size_mm=em_size,
                            **dict(_optional_mapping(
                                _optional_mapping(layout_config, "text_decorations"),
                                "underline",
                            )),
                        )
                        for decoration in decorations:
                            decoration.id = len(state.graphics)
                            state.graphics.append(decoration)
                        underline_count += len(decorations)
                        add_source_id(element.id)
                    if any(
                        _text_width(token, font, scale) > usable_width
                        for token in paragraph.split()
                    ):
                        state.warnings.append("forced_word_break")
                    state.text_fragments.append(paragraph)
                    if paragraph_index < len(normalized_paragraphs) - 1:
                        state.text_fragments.append("\n")
                    if state.cursor_y + paragraph_spacing <= content_bottom + 1e-9:
                        state.cursor_y += paragraph_spacing
                element_formulas = [
                    formula for formula in rendered_formulas
                    if formula.element_id.startswith(f"{element.id}-formula-")
                ]
                details[element.id] = {
                    "type": "text",
                    "characters": sum(map(len, element.paragraphs)),
                    "formulas": [asdict(formula) for formula in element_formulas],
                }
                continue

            if isinstance(element, SourceTableElement):
                if state.has_content:
                    state.cursor_y += spacing_before
                table_count += 1
                table_cells += len(element.cells)
                next_row = 0
                fragment_index = 0
                row_height = table_row_height(dict(size_options))
                while next_row < element.rows:
                    available = content_bottom - state.cursor_y
                    rows_fit = int(available // row_height)
                    if rows_fit <= 0:
                        if not enabled:
                            raise ValueError(OVERFLOW_ERROR)
                        finish_page()
                        continue
                    headers = (
                        list(range(element.repeat_header_rows))
                        if next_row > 0 and element.repeat_header_rows
                        else []
                    )
                    data_capacity = rows_fit - len(headers)
                    if data_capacity <= 0:
                        raise ValueError("Table header leaves no room for a data row")
                    selected = headers + list(
                        range(next_row, min(element.rows, next_row + data_capacity))
                    )
                    fragment = layout_table_fragment(
                        element, selected, font, x=left, y=state.cursor_y,
                        width=usable_width, size_options=dict(size_options),
                    )
                    for glyph in fragment.glyphs:
                        state.glyphs.append(replace(
                            glyph, glyph_index=len(state.glyphs),
                            line_index=state.line_count + glyph.line_index,
                        ))
                    for stroke in fragment.strokes:
                        state.graphics.append(replace(stroke, id=len(state.graphics)))
                    state.line_count += max(1, len(selected))
                    state.cursor_y += fragment.height_mm + spacing_after
                    add_source_id(element.id)
                    fragment_index += 1
                    state.table_fragments.append({
                        "table_id": element.id,
                        "rows": selected,
                        "continued_from_previous": next_row > 0,
                        "continues_next": selected[-1] < element.rows - 1,
                        "border_strokes": fragment.border_count,
                    })
                    table_pages.add((element.id, len(pages)))
                    data_rows = [row for row in selected if row >= next_row]
                    next_row = data_rows[-1] + 1
                    if next_row < element.rows:
                        finish_page()
                details[element.id] = {
                    "type": "table", "rows": element.rows, "columns": element.columns,
                    "cells": len(element.cells),
                    "merged_cells": sum(
                        cell.row_span > 1 or cell.column_span > 1 for cell in element.cells
                    ),
                    "pages": sum(table_id == element.id for table_id, _ in table_pages),
                }
                continue

            if isinstance(element, (SourceLineElement, SourceArrowElement)):
                required_before = spacing_before if state.has_content else 0.0
                source_strokes = (
                    line_strokes(element) if isinstance(element, SourceLineElement)
                    else arrow_strokes(element)
                )
                if not source_strokes:
                    continue
                xs = [point.x for stroke in source_strokes for point in stroke.points]
                ys = [point.y for stroke in source_strokes for point in stroke.points]
                width = max(xs) - min(xs)
                height = max(ys) - min(ys)
                ensure_height(required_before + max(height, 0.5))
                state.cursor_y += required_before
                x_offset = left - min(xs)
                y_offset = state.cursor_y - min(ys)
                for stroke in source_strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics),
                        points=[Point(point.x + x_offset, point.y + y_offset) for point in stroke.points],
                    ))
                state.cursor_y += max(height, 0.5) + spacing_after
                add_source_id(element.id)
                if isinstance(element, SourceLineElement):
                    if element.semantic_role == "underline":
                        underline_count += 1
                    else:
                        line_count_semantic += 1
                else:
                    arrow_count += 1
                details[element.id] = {
                    "type": "line" if isinstance(element, SourceLineElement) else "arrow",
                    "strokes": len(source_strokes),
                }
                continue

            required_before = spacing_before if state.has_content else 0.0
            if isinstance(element, SourceMathElement):
                if renderer is None:
                    warning = f"math_element_skipped_latex_off: {element.id}"
                    warnings.append(warning)
                    details[element.id] = {"type": "math", "skipped": True, "warning": warning}
                    continue
                formula_index += 1
                if document_layout_mode != "reflow" and state.exclusion_zones:
                    state.cursor_y = _clear_blocking_zones(
                        state.cursor_y, line_advance, state.exclusion_zones
                    )
                try:
                    rendered_visual = (
                        render_visual_math_image(
                            element.visual_image_path,
                            element.expression,
                            element.visual_ppmm or float(latex_config.get("render_ppmm", 24.0)),
                            latex_config,
                            strict_quality=bool(strict_latex_quality),
                        )
                        if element.visual_image_path is not None
                        else None
                    )
                    rich_line = layout_math_element(
                        element.expression,
                        usable_width,
                        dict(size_options),
                        latex_config,
                        renderer,
                        formula_index=formula_index,
                        element_id=element.id,
                        source_syntax=element.source_syntax,
                        display_mode=element.display_mode,
                        source_page_index=element.source_page_index,
                        debug_dir=latex_debug_dir,
                        rendered_math=rendered_visual,
                    )
                except ValueError as error:
                    raise ValueError(
                        f"Source page {element.source_page_index + 1}, "
                        f"source element {element.id!r}: {error}"
                    ) from error
                required = (
                    rich_line.spacing_before_mm
                    + rich_line.advance_mm
                    + rich_line.spacing_after_mm
                )
                ensure_height(required)
                state.cursor_y += rich_line.spacing_before_mm
                for stroke in rich_line.formula_strokes:
                    state.graphics.append(replace(
                        stroke,
                        id=len(state.graphics),
                        source_page_index=element.source_page_index,
                        points=[
                            Point(left + point.x, state.cursor_y + point.y)
                            for point in stroke.points
                        ],
                    ))
                source_bbox = (
                    {
                        "x0": element.bbox.x0,
                        "y0": element.bbox.y0,
                        "x1": element.bbox.x1,
                        "y1": element.bbox.y1,
                    }
                    if element.bbox is not None
                    else None
                )
                placed_infos = _place_formula_infos(
                    rich_line.formula_infos,
                    left,
                    state.cursor_y,
                    source_bbox=source_bbox,
                )
                state.formulas.extend(placed_infos)
                rendered_formulas.extend(placed_infos)
                state.warnings.extend(rich_line.warnings)
                state.cursor_y += rich_line.advance_mm + rich_line.spacing_after_mm
                state.line_count += 1
                add_source_id(element.id)
                details[element.id] = {
                    "type": "math",
                    "source_syntax": element.source_syntax,
                    "expression": element.expression,
                    "formula_index": formula_index,
                }
                continue

            if isinstance(element, SourceRasterImageElement):
                image_found += 1
                if image_mode == "off":
                    warnings.append(f"image_skipped_images_off: {element.id}")
                    details[element.id] = {"type": "raster-image", "mode": "off", "skipped": True}
                    continue
                width, height = _image_size(
                    element, usable_width, content_bottom - top,
                    default_width_ratio, max_height_ratio,
                )
                mapped = _mapped_element_rect(
                    element.bbox,
                    source_page.width_mm,
                    source_page.height_mm,
                    content_rect,
                    float(preserve_config.get("max_upscale", 1.10)),
                )
                if (
                    document_layout_mode == "hybrid"
                    and mapped is not None
                    and element.relative_to_v not in {"page", "margin"}
                ):
                    mapped = RectMM(
                        mapped.x,
                        state.cursor_y + required_before,
                        width,
                        height,
                    )
                was_preplaced = element.id in preplacements
                if was_preplaced:
                    output_rect, mapped, effective_wrap, placement_warnings = preplacements[
                        element.id
                    ]
                else:
                    output_rect, effective_wrap, placement_warnings = _place_raster(
                        element,
                        document_layout_mode,
                        mapped,
                        width,
                        height,
                        state.cursor_y,
                        content_rect,
                        state.placements,
                        hybrid_config,
                        spacing_before,
                    )
                state.warnings.extend(
                    f"{warning}: {element.id}" for warning in placement_warnings
                )
                if document_layout_mode == "reflow" or element.wrap_mode == "inline":
                    ensure_height(required_before + output_rect.height)
                    state.cursor_y += required_before
                    output_rect = RectMM(
                        output_rect.x,
                        state.cursor_y,
                        output_rect.width,
                        output_rect.height,
                    )
                elif output_rect.bottom > content_bottom + 1e-9:
                    if not enabled:
                        raise ValueError(OVERFLOW_ERROR)
                    finish_page()
                    output_rect = RectMM(
                        output_rect.x,
                        top,
                        output_rect.width,
                        output_rect.height,
                    )
                debug_path = image_debug_dir / f"{element.id}.png" if image_debug_dir else None
                prepared = preprocess_image(element.image_path, image_options, debug_path=debug_path)
                vectorized = vectorize_image(
                    prepared,
                    image_options,
                    mode=image_mode,
                    width_mm=output_rect.width,
                    height_mm=output_rect.height,
                    element_id=element.id, source_path=str(element.image_path),
                )
                for stroke in vectorized.strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics),
                        points=[
                            Point(point.x + output_rect.x, point.y + output_rect.y)
                            for point in stroke.points
                        ],
                    ))
                if document_layout_mode == "reflow" or element.wrap_mode == "inline":
                    state.cursor_y += output_rect.height + spacing_after
                elif effective_wrap == "top_bottom":
                    state.cursor_y = max(state.cursor_y, output_rect.bottom + spacing_after)
                elif effective_wrap == "square" and not was_preplaced:
                    state.exclusion_zones.append(ExclusionZone(
                        output_rect,
                        element.wrap_side,
                        element.id,
                        element.distance_left_mm
                        or float(hybrid_config.get("image_padding_mm", 2.0)),
                        element.distance_right_mm
                        or float(hybrid_config.get("image_padding_mm", 2.0)),
                        element.distance_top_mm,
                        element.distance_bottom_mm,
                    ))
                add_source_id(element.id)
                image_vectorized += int(bool(vectorized.strokes))
                image_strokes += len(vectorized.strokes)
                image_points += vectorized.point_count
                state.warnings.extend(f"{warning}: {element.id}" for warning in vectorized.warnings)
                placement = _placement_record(
                    element.id,
                    element.source_page_index,
                    element.bbox,
                    mapped,
                    output_rect,
                    element.anchor_type,
                    effective_wrap,
                    element.wrap_side,
                    element.displayed_width,
                    placement_warnings,
                    "raster-image",
                )
                state.placements.append(placement)
                placement_records.append(placement)
                details[element.id] = {
                    "type": "raster-image", "mode": vectorized.mode,
                    "width_mm": round(output_rect.width, 4),
                    "height_mm": round(output_rect.height, 4),
                    "strokes": len(vectorized.strokes), "points": vectorized.point_count,
                    **placement,
                }
                continue

            if isinstance(element, SourceVectorElement):
                vector_count += 1
                width, height = _vector_size(element, usable_width, content_bottom - top)
                mapped = _mapped_element_rect(
                    element.bbox,
                    source_page.width_mm,
                    source_page.height_mm,
                    content_rect,
                    float(preserve_config.get("max_upscale", 1.10)),
                )
                was_preplaced = element.id in preplacements
                if was_preplaced:
                    output_rect, mapped, effective_wrap, placement_warnings = preplacements[
                        element.id
                    ]
                else:
                    output_rect, effective_wrap, placement_warnings = _place_vector(
                        element,
                        document_layout_mode,
                        mapped,
                        width,
                        height,
                        state.cursor_y,
                        content_rect,
                        state.placements,
                        hybrid_config,
                        spacing_before,
                    )
                if document_layout_mode == "reflow":
                    ensure_height(required_before + output_rect.height)
                    state.cursor_y += required_before
                    output_rect = RectMM(
                        output_rect.x,
                        state.cursor_y,
                        output_rect.width,
                        output_rect.height,
                    )
                state.warnings.extend(
                    f"{warning}: {element.id}" for warning in placement_warnings
                )
                source_points = [point for stroke in element.strokes for point in stroke.points]
                min_x = min(point.x for point in source_points)
                min_y = min(point.y for point in source_points)
                source_width = max(point.x for point in source_points) - min_x
                source_height = max(point.y for point in source_points) - min_y
                vector_scale = min(
                    output_rect.width / max(source_width, 1e-9),
                    output_rect.height / max(source_height, 1e-9),
                )
                for stroke in element.strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics), element_id=element.id,
                        element_type="pdf-vector",
                        points=[
                            Point(
                                output_rect.x + (point.x - min_x) * vector_scale,
                                output_rect.y + (point.y - min_y) * vector_scale,
                            )
                            for point in stroke.points
                        ],
                    ))
                if document_layout_mode == "reflow":
                    state.cursor_y += output_rect.height + spacing_after
                elif effective_wrap == "top_bottom":
                    state.cursor_y = max(state.cursor_y, output_rect.bottom + spacing_after)
                elif effective_wrap == "square" and not was_preplaced:
                    state.exclusion_zones.append(ExclusionZone(
                        output_rect,
                        element.wrap_side,
                        element.id,
                        padding_left_mm=float(hybrid_config.get("image_padding_mm", 2.0)),
                        padding_right_mm=float(hybrid_config.get("image_padding_mm", 2.0)),
                    ))
                add_source_id(element.id)
                placement = _placement_record(
                    element.id,
                    element.source_page_index,
                    element.bbox,
                    mapped,
                    output_rect,
                    element.anchor_type,
                    effective_wrap,
                    element.wrap_side,
                    width,
                    placement_warnings,
                    "pdf-vector",
                )
                state.placements.append(placement)
                placement_records.append(placement)
                details[element.id] = {
                    "type": "pdf-vector",
                    "strokes": len(element.strokes),
                    **placement,
                }

    finish_page()
    if not pages:
        raise ValueError("Document contains no drawable text or images")
    stats = {
        "source_pages": len(document.pages),
        "text_elements": sum(isinstance(item, SourceTextElement) for item in document.elements),
        "math_elements": sum(isinstance(item, SourceMathElement) for item in document.elements),
        "raster_images_found": image_found,
        "raster_images_vectorized": image_vectorized,
        "pdf_vector_elements": vector_count,
        "images_skipped": image_found - image_vectorized,
        "image_strokes": image_strokes,
        "image_points": image_points,
        "underlines": underline_count,
        "generic_lines": line_count_semantic,
        "arrows": arrow_count,
        "tables": table_count,
        "table_cells": table_cells,
        "table_pages": len(table_pages),
    }
    latex_stats = {
        "enabled": renderer is not None,
        "backend": "mathtext" if renderer is not None else "off",
        "expressions_found": len(rendered_formulas),
        "inline_expressions": sum(not formula.display_mode for formula in rendered_formulas),
        "block_expressions": sum(formula.display_mode for formula in rendered_formulas),
        "rendered": len(rendered_formulas),
        "semantic_expressions": sum(
            formula.source_kind == "semantic-latex" for formula in rendered_formulas
        ),
        "omml_expressions": sum(
            formula.source_syntax == "omml" for formula in rendered_formulas
        ),
        "pdf_visual_expressions": sum(
            formula.source_syntax == "pdf-visual" for formula in rendered_formulas
        ),
        "outline_fallbacks": sum(
            "latex_centerline_outline_fallback" in formula.warnings
            for formula in rendered_formulas
        ),
        "fallbacks": sum(bool(formula.warnings) for formula in rendered_formulas),
        "strokes": sum(formula.strokes for formula in rendered_formulas),
        "points": sum(formula.points for formula in rendered_formulas),
        "pen_lifts": sum(formula.strokes for formula in rendered_formulas),
        "needs_review": sum(
            bool((formula.quality or {}).get("needs_review")) for formula in rendered_formulas
        ),
        "warnings": sorted({warning for formula in rendered_formulas for warning in formula.warnings}),
        "formulas": [asdict(formula) for formula in rendered_formulas],
        "unsupported": [
            "full LaTeX documents and packages",
            "TikZ, user macros, bibliography, and file includes",
            "external LaTeX or shell execution",
            "full OMML conversion",
            "LaTeX reconstruction from PDF",
        ],
    }
    layout_stats = _layout_statistics(
        document_layout_mode,
        placement_records,
        all_line_boxes,
    )
    if layout_debug_dir is not None:
        export_layout_debug(
            layout_debug_dir,
            page,
            placement_records,
            all_line_boxes,
        )
    return PaginatedLayout(
        pages,
        list(dict.fromkeys(warnings)),
        stats,
        details,
        latex_stats,
        layout_stats,
    )


def add_page_numbers(
    paginated: PaginatedLayout,
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    footer_options: Mapping[str, object],
    number_size_options: Mapping[str, object],
    *,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> None:
    if not footer_options.get("enabled", True):
        return
    page_count = len(paginated.pages)
    label_format = str(footer_options.get("format", "{page}"))
    baseline = page.height_mm - _number(footer_options, "baseline_from_bottom_mm")
    for page_layout in paginated.pages:
        label = label_format.format(page=page_layout.page_index + 1, pages=page_count)
        font.validate_text(label)
        measured = layout_text(
            [label], font, PageSpec("footer", page.width_mm, 1000.0),
            {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
            number_size_options, engine=engine, language=language, script=script,
            direction=direction, features=features,
        )
        width = sum(glyph.advance_mm for glyph in measured.glyphs)
        start_x = (page.width_mm - width) / 2
        first_x = measured.glyphs[0].x_mm if measured.glyphs else 0.0
        number_indices: list[int] = []
        for glyph in measured.glyphs:
            index = len(page_layout.layout.glyphs)
            number_indices.append(index)
            page_layout.layout.glyphs.append(replace(
                glyph, x_mm=start_x + glyph.x_mm - first_x,
                baseline_y_mm=baseline, glyph_index=index,
                line_index=page_layout.layout.line_count,
            ))
        page_layout.layout.line_count += 1
        page_layout.metadata.update({
            "page_number": page_layout.page_index + 1,
            "page_number_text": label,
            "page_number_glyph_indices": number_indices,
            "page_number_width_mm": width,
            "page_number_center_x_mm": start_x + width / 2,
        })


def _image_size(
    element: SourceRasterImageElement, usable_width: float, usable_height: float,
    default_width_ratio: float, max_height_ratio: float,
) -> tuple[float, float]:
    width = element.displayed_width or usable_width * default_width_ratio
    height = element.displayed_height or width * element.height_px / max(1, element.width_px)
    scale = min(1.0, usable_width / width, usable_height * max_height_ratio / height)
    return width * scale, height * scale


def _place_formula_infos(
    formulas: list[FormulaInfo],
    x_offset: float,
    y_offset: float,
    *,
    source_bbox: dict[str, float] | None = None,
) -> list[FormulaInfo]:
    result: list[FormulaInfo] = []
    for formula in formulas:
        target = formula.target_bbox
        translated = (
            {
                "x": float(target["x"]) + x_offset,
                "y": float(target["y"]) + y_offset,
                "width": float(target["width"]),
                "height": float(target["height"]),
            }
            if target is not None
            else None
        )
        result.append(replace(
            formula,
            source_bbox=source_bbox or formula.source_bbox,
            target_bbox=translated,
        ))
    return result


def _vector_size(
    element: SourceVectorElement, usable_width: float, usable_height: float
) -> tuple[float, float]:
    points = [point for stroke in element.strokes for point in stroke.points]
    width = max(point.x for point in points) - min(point.x for point in points)
    height = max(point.y for point in points) - min(point.y for point in points)
    scale = min(1.0, usable_width / max(width, 1e-9), usable_height * 0.6 / max(height, 1e-9))
    return max(width * scale, 0.1), max(height * scale, 0.1)


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid mapping field: pagination.{key}")
    return value


def _text_width(text: str, font: LoadedFont, scale: float) -> float:
    return sum(
        font.advance_for_glyph(font.glyph_name_for_char(character)) * scale
        for character in text
    )


def _merge_multiline_math_blocks(lines: list[str]) -> list[str]:
    merged: list[str] = []
    pending: list[str] = []
    closer: str | None = None
    for line in lines:
        if closer is not None:
            pending.append(line)
            if closer in line:
                merged.append("\n".join(pending))
                pending = []
                closer = None
            continue
        candidates = [
            (position, opener, ending)
            for opener, ending in (("$$", "$$"), (r"\[", r"\]"))
            if (position := line.find(opener)) >= 0
        ]
        if not candidates:
            merged.append(line)
            continue
        position, opener, ending = min(candidates)
        if line.find(ending, position + len(opener)) >= 0:
            merged.append(line)
            continue
        pending = [line]
        closer = ending
    if pending:
        merged.append("\n".join(pending))
    return merged


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid non-negative field: {key}")
    return float(value)


def _optional_mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"document_layout.{key} must be a mapping")
    return value


def _mapped_element_rect(
    bbox: object,
    source_width: float | None,
    source_height: float | None,
    content_rect: RectMM,
    max_upscale: float,
) -> RectMM | None:
    if bbox is None or source_width is None or source_height is None:
        return None
    source_rect = RectMM(bbox.x0, bbox.y0, bbox.width, bbox.height)
    return map_source_rect(
        source_rect,
        (source_width, source_height),
        content_rect,
        max_upscale=max_upscale,
    )


def _place_raster(
    element: SourceRasterImageElement,
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
) -> tuple[RectMM, str, list[str]]:
    inline = element.wrap_mode == "inline" or element.anchor_type == "flow"
    return _place_graphic(
        mode,
        mapped,
        width,
        height,
        cursor_y,
        content,
        previous,
        options,
        spacing_before,
        element.wrap_mode,
        inline=inline,
        source_position_available=element.bbox is not None,
        relative_to_v=element.relative_to_v,
    )


def _place_vector(
    element: SourceVectorElement,
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
) -> tuple[RectMM, str, list[str]]:
    return _place_graphic(
        mode,
        mapped,
        width,
        height,
        cursor_y,
        content,
        previous,
        options,
        spacing_before,
        element.wrap_mode,
        inline=False,
        source_position_available=element.bbox is not None,
        relative_to_v="page",
    )


def _place_graphic(
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
    wrap_mode: str,
    *,
    inline: bool,
    source_position_available: bool,
    relative_to_v: str | None,
) -> tuple[RectMM, str, list[str]]:
    warnings: list[str] = []
    if mode == "reflow" or inline:
        return (
            RectMM(
                content.x + (content.width - width) / 2,
                cursor_y + spacing_before,
                width,
                height,
            ),
            "inline" if inline else "top_bottom",
            warnings,
        )
    if mapped is None:
        warnings.append("image_source_position_unavailable")
        rect = RectMM(content.x, cursor_y + spacing_before, width, height)
    elif mode == "preserve":
        rect = mapped
    else:
        x = min(max(mapped.x, content.x), content.right - width)
        y = mapped.y if relative_to_v in {"page", "margin"} else cursor_y + spacing_before
        y = min(max(y, content.y), content.bottom - height)
        rect = RectMM(x, y, width, height)
    effective_wrap = wrap_mode
    if mode == "hybrid" and effective_wrap == "none":
        effective_wrap = "square"
        warnings.append("image_wrap_none_approximated_as_square")
    if mode == "hybrid":
        max_shift = float(options.get("max_vertical_shift_mm", 25.0))
        attempts = max(1, int(options.get("max_placement_attempts", 20)))
        initial_y = rect.y
        for _attempt in range(attempts):
            conflicts = [
                existing
                for item in previous
                if (existing := _payload_rect(item.get("output_bbox_mm"))) is not None
                and intersection_area(rect, existing) > 1e-9
            ]
            if not conflicts:
                break
            next_y = max(conflict.bottom for conflict in conflicts) + float(
                options.get("image_padding_mm", 2.0)
            )
            if next_y - initial_y > max_shift or next_y + rect.height > content.bottom:
                effective_wrap = "top_bottom"
                warnings.append("image_wrap_fallback_top_bottom")
                rect = RectMM(rect.x, max(cursor_y + spacing_before, initial_y), rect.width, rect.height)
                break
            rect = RectMM(rect.x, next_y, rect.width, rect.height)
            warnings.append("image_overlap_avoided")
    clamped = RectMM(
        min(max(rect.x, content.x), content.right - rect.width),
        min(max(rect.y, content.y), content.bottom - rect.height),
        min(rect.width, content.width),
        min(rect.height, content.height),
    )
    if center_displacement(rect, clamped) > 1e-6:
        warnings.append("image_position_shifted")
    if not source_position_available and "image_source_position_unavailable" not in warnings:
        warnings.append("image_source_position_unavailable")
    return clamped, effective_wrap, list(dict.fromkeys(warnings))


def _placement_record(
    element_id: str,
    source_page_index: int,
    source_bbox: object,
    mapped: RectMM | None,
    output: RectMM,
    anchor: str,
    wrap_mode: str,
    wrap_side: str,
    original_width: float | None,
    warnings: list[str],
    element_type: str,
) -> dict[str, object]:
    source_rect = (
        RectMM(source_bbox.x0, source_bbox.y0, source_bbox.width, source_bbox.height)
        if source_bbox is not None
        else None
    )
    displacement = center_displacement(mapped, output) if mapped is not None else None
    scale = output.width / original_width if original_width and original_width > 0 else 1.0
    return {
        "id": element_id,
        "element_type": element_type,
        "source_page_index": source_page_index,
        "source_bbox_mm": rect_payload(source_rect),
        "mapped_bbox_mm": rect_payload(mapped),
        "output_bbox_mm": rect_payload(output),
        "target_page_index": source_page_index,
        "anchor": anchor,
        "wrap_mode": wrap_mode,
        "wrap_side": wrap_side,
        "scale": round(scale, 6),
        "center_displacement_mm": round(displacement, 6) if displacement is not None else None,
        "overlap_area_mm2": 0.0,
        "page_overflow_area_mm2": 0.0,
        "fallbacks": list(dict.fromkeys(warnings)),
    }


def _payload_rect(value: object) -> RectMM | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return RectMM(
            float(value["x"]),
            float(value["y"]),
            float(value["width"]),
            float(value["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _clear_blocking_zones(
    cursor_y: float,
    height: float,
    zones: list[ExclusionZone],
) -> float:
    current = cursor_y
    while True:
        blockers = [
            zone.padded_bbox
            for zone in zones
            if not (current + height <= zone.padded_bbox.y or current >= zone.padded_bbox.bottom)
        ]
        if not blockers:
            return current
        current = max(box.bottom for box in blockers)


def _layout_text_around_zones(
    paragraph: str,
    state: _PageState,
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    size_options: Mapping[str, object],
    content_bottom: float,
    glyph_height: float,
    line_advance: float,
    scale: float,
    add_source_id,
    element_id: str,
    *,
    tab_spaces: int,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> None:
    remaining = paragraph.strip()
    left = _number(margins, "left")
    right = page.width_mm - _number(margins, "right")
    while remaining:
        if state.cursor_y + glyph_height > content_bottom + 1e-9:
            raise ValueError(OVERFLOW_ERROR)
        intervals = available_intervals(
            left,
            right,
            state.cursor_y,
            state.cursor_y + line_advance,
            state.exclusion_zones,
        )
        interval = choose_widest_interval(intervals)
        if interval is None:
            state.cursor_y = _clear_blocking_zones(
                state.cursor_y, line_advance, state.exclusion_zones
            )
            continue
        line, remaining = _take_text_line(
            remaining, interval[1] - interval[0], font, scale
        )
        local_margins = dict(margins)
        local_margins.update({
            "left": interval[0],
            "right": page.width_mm - interval[1],
            "top": 0.0,
            "bottom": 0.0,
        })
        flowed = layout_text(
            [line],
            font,
            PageSpec("flow-line", page.width_mm, 1_000_000.0),
            local_margins,
            size_options,
            tab_spaces=tab_spaces,
            engine=engine,
            language=language,
            script=script,
            direction=direction,
            features=features,
        )
        baseline = state.cursor_y + font.metrics.ascent * scale
        global_line = state.line_count
        for glyph in flowed.glyphs:
            state.glyphs.append(replace(
                glyph,
                baseline_y_mm=baseline,
                line_index=global_line,
                glyph_index=len(state.glyphs),
            ))
        used_width = sum(glyph.advance_mm for glyph in flowed.glyphs)
        state.line_boxes.append(RectMM(
            interval[0], state.cursor_y, min(used_width, interval[1] - interval[0]), line_advance
        ))
        state.cursor_y += line_advance
        state.line_count += 1
        add_source_id(element_id)


def _take_text_line(
    text: str, max_width: float, font: LoadedFont, scale: float
) -> tuple[str, str]:
    words = text.split()
    if not words:
        return "", ""
    current = words[0]
    if _text_width(current, font, scale) > max_width:
        split = 1
        while split < len(current) and _text_width(current[: split + 1], font, scale) <= max_width:
            split += 1
        return current[:split], " ".join([current[split:], *words[1:]]).strip()
    consumed = 1
    while consumed < len(words):
        candidate = f"{current} {words[consumed]}"
        if _text_width(candidate, font, scale) > max_width:
            break
        current = candidate
        consumed += 1
    return current, " ".join(words[consumed:])


def _layout_statistics(
    mode: str,
    placements: list[dict[str, object]],
    line_boxes: list[dict[str, object]],
) -> dict[str, object]:
    displacements = [
        float(value)
        for item in placements
        if (value := item.get("center_displacement_mm")) is not None
    ]
    scales = [float(item.get("scale", 1.0)) for item in placements]
    overlaps = 0.0
    for item in placements:
        image = _payload_rect(item.get("output_bbox_mm"))
        if image is None:
            continue
        for line in line_boxes:
            if int(line.get("page_index", -1)) != int(item.get("target_page_index", -2)):
                continue
            text = _payload_rect(line.get("bbox"))
            if text is not None:
                overlaps += intersection_area(image, text)
    threshold = 1.0 if mode == "preserve" else 10.0
    return {
        "mode": mode,
        "images": len(placements),
        "images_with_source_bbox": sum(
            item.get("source_bbox_mm") is not None for item in placements
        ),
        "images_wrapped": sum(item.get("wrap_mode") == "square" for item in placements),
        "images_top_bottom": sum(
            item.get("wrap_mode") == "top_bottom" for item in placements
        ),
        "position_preserved": sum(
            item.get("center_displacement_mm") is not None
            and float(item["center_displacement_mm"]) <= threshold
            for item in placements
        ),
        "position_fallbacks": sum(bool(item.get("fallbacks")) for item in placements),
        "mean_center_displacement_mm": round(
            sum(displacements) / len(displacements), 6
        ) if displacements else None,
        "max_center_displacement_mm": round(max(displacements), 6) if displacements else None,
        "mean_scale_factor": round(sum(scales) / len(scales), 6) if scales else None,
        "overlaps_remaining": round(overlaps, 6),
        "page_overflow_area_mm2": round(
            sum(float(item.get("page_overflow_area_mm2", 0.0)) for item in placements), 6
        ),
        "elements": placements,
    }
