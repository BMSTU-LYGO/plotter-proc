from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path

from plotter_processor.document_models import (
    SourceArrowElement,
    SourceDocument,
    SourceLineElement,
    SourceMathElement,
    SourceParagraph,
    SourceRasterImageElement,
    SourceTableElement,
    SourceTextElement,
    SourceTextRun,
    SourceVectorElement,
)
from plotter_processor.font_loader import LoadedFont
from plotter_processor.graphic_placement import payload_rect as _payload_rect
from plotter_processor.graphic_placement import place_raster as _place_raster
from plotter_processor.graphic_placement import place_vector as _place_vector
from plotter_processor.graphic_placement import placement_record as _placement_record
from plotter_processor.graphic_placement import rotate_image_point as _rotate_image_point
from plotter_processor.graphic_placement import rotated_size as _rotated_size
from plotter_processor.graphic_placement import scaled_padding as _scaled_padding
from plotter_processor.image_preprocessor import preprocess_image
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.latex_layout import FormulaInfo, layout_latex_paragraph, layout_math_element
from plotter_processor.latex_parser import contains_latex
from plotter_processor.latex_renderer import math_renderer_from_options, render_visual_math_image
from plotter_processor.layout_debug import export_layout_debug
from plotter_processor.layout_models import (
    ExclusionZone,
    PageTransform,
    RectMM,
    available_intervals,
    choose_widest_interval,
    rect_payload,
)
from plotter_processor.layout_reporting import build_layout_statistics as _layout_statistics
from plotter_processor.models import LayoutResult, PageSpec, Point
from plotter_processor.page_grid import resolve_page_grid
from plotter_processor.page_layout_model import (
    AnchoredPlacement,
    LayoutModel,
    PageLayout,
    PageLayoutState,
    PaginatedLayout,
)
from plotter_processor.page_text_flow import (
    clear_blocking_zones as _clear_blocking_zones,
)
from plotter_processor.page_text_flow import (
    layout_text_around_zones as _layout_text_around_zones,
)
from plotter_processor.page_text_flow import (
    prune_expired_zones as _prune_expired_zones,
)
from plotter_processor.page_text_flow import (
    text_width as _text_width,
)
from plotter_processor.page_text_flow import (
    zone_payloads as _zone_payloads,
)
from plotter_processor.paragraph_layout import layout_paragraph
from plotter_processor.performance import StageTimings
from plotter_processor.shape_layout import arrow_strokes, line_strokes
from plotter_processor.table_layout import (
    layout_table_fragment,
    plan_table_layout,
    protected_row_end,
)
from plotter_processor.text_decorations import build_underlines
from plotter_processor.text_normalizer import normalize_text
from plotter_processor.vector_layout import OVERFLOW_ERROR, layout_text

_PageState = PageLayoutState


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
    paragraph_options: Mapping[str, object] | None = None,
    grid_options: Mapping[str, object] | None = None,
    table_options: Mapping[str, object] | None = None,
    layout_debug_dir: Path | None = None,
    preserve_source_page_breaks: bool = True,
    tab_spaces: int = 4,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
    stage_timings: StageTimings | None = None,
) -> LayoutModel:
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
    image_cache_hits = image_cache_misses = image_micro_strokes_suppressed = 0
    underline_count = line_count_semantic = arrow_count = table_count = table_cells = 0
    table_pages: set[tuple[str, int]] = set()
    table_splits = repeated_headers_emitted = shared_borders_suppressed = 0
    formula_index = 0
    rendered_formulas: list[FormulaInfo] = []
    placement_records: list[dict[str, object]] = []
    all_line_boxes: list[dict[str, object]] = []
    trace_records: list[dict[str, object]] = []
    paragraph_records: list[dict[str, object]] = []
    page_transform_records: list[dict[str, object]] = []
    layout_config = dict(document_layout_options or {})
    paragraph_config = dict(paragraph_options or {})
    grid = resolve_page_grid(grid_options)
    if grid.enabled:
        paragraph_config["grid_cell_width_mm"] = grid.cell_width_mm
        for key in ("indent_cells", "first_line_indent_cells", "tab_interval_cells"):
            if key in (grid_options or {}):
                paragraph_config[key] = (grid_options or {})[key]
    table_config = dict(table_options or {})
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

    def finish_page() -> _PageState:
        nonlocal state
        if not state.has_content:
            state.cursor_y = top
            state.exclusion_zones.clear()
            return state
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
        return state

    def ensure_height(required: float) -> None:
        if state.cursor_y + required <= content_bottom + 1e-9:
            return
        if not enabled:
            raise ValueError(OVERFLOW_ERROR)
        finish_page()
        if state.cursor_y + required > content_bottom + 1e-9:
            raise ValueError("An element is taller than the usable page area")

    def record_trace(
        element: object,
        element_type: str,
        cursor_before: float,
        placement_reason: str,
        active_zones_before: list[dict[str, object]],
        *,
        target_bbox: RectMM | None = None,
    ) -> None:
        source_bbox = getattr(element, "bbox", None)
        source_rect = (
            RectMM(source_bbox.x0, source_bbox.y0, source_bbox.width, source_bbox.height)
            if source_bbox is not None
            else None
        )
        trace_records.append({
            "element_id": str(getattr(element, "id", "")),
            "type": element_type,
            "source_order": int(getattr(element, "source_order", -1)),
            "source_bbox": rect_payload(source_rect),
            "target_bbox": rect_payload(target_bbox),
            "anchor_type": getattr(element, "anchor_type", "flow"),
            "wrap_mode": getattr(element, "wrap_mode", "none"),
            "cursor_y_before": round(cursor_before, 6),
            "cursor_y_after": round(state.cursor_y, 6),
            "active_exclusion_zones": active_zones_before,
            "page_index": len(pages),
            "placement_reason": placement_reason,
            "shift_mm": round(state.cursor_y - cursor_before, 6),
        })

    def render_latex_paragraph(
        paragraph: str,
        width: float,
        formula_start: int,
        element: SourceTextElement,
    ):
        if renderer is None:
            raise RuntimeError("LaTeX renderer is not configured")
        timing = stage_timings.measure("latex_render") if stage_timings else nullcontext()
        with timing:
            return layout_latex_paragraph(
                paragraph,
                font,
                width,
                dict(size_options),
                latex_config,
                renderer,
                formula_index_start=formula_start,
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

    for source_page_position, source_page in enumerate(document.pages):
        if source_page_position and preserve_source_page_breaks and state.has_content:
            finish_page()
        source_width = source_page.width_mm or page.width_mm
        source_height = source_page.height_mm or page.height_mm
        source_content = (
            RectMM(
                source_page.content_bbox.x0,
                source_page.content_bbox.y0,
                source_page.content_bbox.width,
                source_page.content_bbox.height,
            )
            if source_page.content_bbox is not None
            else None
        )
        page_transform = PageTransform.create(
            source_width,
            source_height,
            content_rect,
            source_content_rect=source_content,
            max_upscale=float(preserve_config.get("max_upscale", 1.10)),
        )
        transform_payload = page_transform.payload()
        transform_payload["target_width_mm"] = page.width_mm
        transform_payload["target_height_mm"] = page.height_mm
        transform_payload["source_page_index"] = source_page.source_page_index
        transform_payload["target_page_start"] = len(pages)
        page_transform_records.append(transform_payload)
        preplacements: dict[str, AnchoredPlacement] = {}
        if document_layout_mode != "reflow":
            provisional: list[dict[str, object]] = []
            for candidate in source_page.elements:
                if isinstance(candidate, SourceRasterImageElement):
                    if image_mode == "off":
                        continue
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
                        page_transform.scale,
                    )
                    candidate_mapped = _mapped_element_rect(
                        candidate.bbox, page_transform
                    )
                    candidate_width, candidate_height = _rotated_size(
                        candidate_width, candidate_height, candidate.rotation_deg
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
                        candidate,
                        usable_width,
                        content_bottom - top,
                        page_transform.scale,
                    )
                    candidate_mapped = _mapped_element_rect(
                        candidate.bbox, page_transform
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
                activate_early = isinstance(candidate, SourceVectorElement) or (
                    isinstance(candidate, SourceRasterImageElement)
                    and (
                        candidate.anchor_type == "absolute"
                        or candidate.relative_to_v in {"page", "margin"}
                    )
                )
                prepared_placement = AnchoredPlacement(
                    candidate.id,
                    candidate.source_order,
                    candidate_rect,
                    candidate_mapped,
                    candidate_wrap,
                    candidate.anchor_type,
                    candidate_warnings,
                    active=activate_early,
                )
                preplacements[candidate.id] = prepared_placement
                provisional.append({"output_bbox_mm": rect_payload(candidate_rect)})
                zone_wrap = candidate_wrap
                if document_layout_mode == "preserve" and zone_wrap == "none":
                    zone_wrap = "square"
                if activate_early and zone_wrap in {"square", "top_bottom"}:
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
                normalized_models: list[SourceParagraph] = []
                for raw_index, raw_paragraph in enumerate(element.paragraphs):
                    source_model = (
                        element.styled_paragraphs[raw_index]
                        if raw_index < len(element.styled_paragraphs)
                        else SourceParagraph((SourceTextRun(raw_paragraph),), semantic_role="body")
                    )
                    normalized, normalization_warnings = normalize_text(
                        raw_paragraph, preserve_tabs=bool(source_model.tab_stops)
                    )
                    warnings.extend(normalization_warnings)
                    pieces = normalized.split("\n")
                    normalized_paragraphs.extend(pieces)
                    for piece in pieces:
                        if piece == source_model.text:
                            normalized_models.append(source_model)
                        else:
                            style = source_model.runs[0].style if source_model.runs else None
                            run = SourceTextRun(piece, style) if style is not None else SourceTextRun(piece)
                            normalized_models.append(replace(source_model, runs=(run,)))
                normalized_paragraphs = _merge_multiline_math_blocks(normalized_paragraphs)
                if len(normalized_models) != len(normalized_paragraphs):
                    normalized_models = [
                        SourceParagraph((SourceTextRun(text),), semantic_role="body")
                        for text in normalized_paragraphs
                    ]
                for paragraph_index, paragraph in enumerate(normalized_paragraphs):
                    paragraph_model = normalized_models[paragraph_index]
                    cursor_before = state.cursor_y
                    zones_before = _zone_payloads(state.exclusion_zones)
                    paragraph_glyph_start = len(state.glyphs)
                    if not paragraph:
                        ensure_height(line_advance)
                        state.cursor_y += line_advance
                        state.text_fragments.append("\n")
                        add_source_id(element.id)
                        record_trace(
                            element, "text", cursor_before, "explicit_blank_paragraph",
                            zones_before,
                        )
                        continue
                    if renderer is not None and contains_latex(paragraph):
                        rich_left = left
                        rich_width = usable_width
                        if document_layout_mode != "reflow" and state.exclusion_zones:
                            _prune_expired_zones(state.exclusion_zones, state.cursor_y)
                            interval = choose_widest_interval(available_intervals(
                                left,
                                left + usable_width,
                                state.cursor_y,
                                state.cursor_y + line_advance,
                                state.exclusion_zones,
                            ))
                            if interval is None:
                                state.cursor_y = _clear_blocking_zones(
                                    state.cursor_y, line_advance, state.exclusion_zones
                                )
                                _prune_expired_zones(state.exclusion_zones, state.cursor_y)
                                interval = choose_widest_interval(available_intervals(
                                    left,
                                    left + usable_width,
                                    state.cursor_y,
                                    state.cursor_y + line_advance,
                                    state.exclusion_zones,
                                ))
                            if interval is not None:
                                rich_left = interval[0]
                                rich_width = interval[1] - interval[0]
                        try:
                            formula_index_before = formula_index
                            rich_lines, formula_index = render_latex_paragraph(
                                paragraph, rich_width, formula_index_before, element
                            )
                            rich_height = sum(
                                line.spacing_before_mm
                                + line.advance_mm
                                + line.spacing_after_mm
                                for line in rich_lines
                            )
                            if document_layout_mode != "reflow" and state.exclusion_zones:
                                actual_interval = choose_widest_interval(available_intervals(
                                    left,
                                    left + usable_width,
                                    state.cursor_y,
                                    state.cursor_y + rich_height,
                                    state.exclusion_zones,
                                ))
                                if actual_interval is None:
                                    state.cursor_y = _clear_blocking_zones(
                                        state.cursor_y, rich_height, state.exclusion_zones
                                    )
                                    _prune_expired_zones(
                                        state.exclusion_zones, state.cursor_y
                                    )
                                    actual_interval = (left, left + usable_width)
                                actual_left = actual_interval[0]
                                actual_width = actual_interval[1] - actual_interval[0]
                                if (
                                    abs(actual_left - rich_left) > 1e-9
                                    or abs(actual_width - rich_width) > 1e-9
                                ):
                                    rich_left = actual_left
                                    rich_width = actual_width
                                    rich_lines, formula_index = render_latex_paragraph(
                                        paragraph,
                                        rich_width,
                                        formula_index_before,
                                        element,
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
                                    x_mm=rich_left + glyph.x_mm,
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
                                        Point(rich_left + point.x, state.cursor_y + point.y)
                                        for point in stroke.points
                                    ],
                                ))
                            placed_infos = _place_formula_infos(
                                rich_line.formula_infos, rich_left, state.cursor_y
                            )
                            state.formulas.extend(placed_infos)
                            rendered_formulas.extend(placed_infos)
                            state.warnings.extend(rich_line.warnings)
                            line_x_values = [
                                value
                                for glyph in rich_line.glyphs
                                for value in (
                                    rich_left + glyph.x_mm,
                                    rich_left + glyph.x_mm + glyph.advance_mm,
                                )
                            ]
                            line_x_values.extend(
                                rich_left + point.x
                                for stroke in rich_line.formula_strokes
                                for point in stroke.points
                            )
                            if line_x_values:
                                state.line_boxes.append(RectMM(
                                    min(line_x_values),
                                    state.cursor_y,
                                    max(line_x_values) - min(line_x_values),
                                    rich_line.advance_mm,
                                ))
                            state.cursor_y += rich_line.advance_mm + rich_line.spacing_after_mm
                            state.line_count += 1
                            add_source_id(element.id)
                        state.text_fragments.append(paragraph)
                        if paragraph_index < len(normalized_paragraphs) - 1:
                            state.text_fragments.append("\n")
                        if state.cursor_y + paragraph_spacing <= content_bottom + 1e-9:
                            state.cursor_y += paragraph_spacing
                        record_trace(
                            element, "text", cursor_before, "latex_in_flow", zones_before,
                        )
                        continue
                    if (
                        document_layout_mode != "reflow"
                        and paragraph_model.tab_stops
                        and state.exclusion_zones
                    ):
                        state.cursor_y = max(
                            state.cursor_y,
                            max(zone.padded_bbox.bottom for zone in state.exclusion_zones),
                        )
                        _prune_expired_zones(state.exclusion_zones, state.cursor_y)
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
                            finish_page,
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
                        record_trace(
                            element, "text", cursor_before, "flow_around_active_zone",
                            zones_before,
                        )
                        continue
                    try:
                        flowed = layout_paragraph(
                            paragraph_model,
                            font,
                            content_left_mm=left,
                            content_right_mm=left + usable_width,
                            base_size_options=size_options,
                            paragraph_options=paragraph_config,
                            engine=engine,
                            language=language,
                            script=script,
                            direction=direction,
                            features=features,
                            tab_scale=(
                                page_transform.scale
                                if document_layout_mode != "reflow"
                                else 1.0
                            ),
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
                    if flowed.space_before_mm:
                        ensure_height(flowed.space_before_mm + flowed.lines[0].advance_mm)
                        state.cursor_y += flowed.space_before_mm
                    first_page_index = len(pages)
                    first_line_left = flowed.lines[0].left_mm
                    for source_line in flowed.lines:
                        line_scale = scale * flowed.font_scale
                        ascent = font.metrics.ascent * line_scale
                        baseline = grid.baseline_at_or_after(state.cursor_y + ascent)
                        line_top = baseline - ascent
                        ensure_height(line_top - state.cursor_y + source_line.advance_mm)
                        baseline = grid.baseline_at_or_after(state.cursor_y + ascent)
                        line_top = baseline - ascent
                        global_line = state.line_count
                        for glyph in source_line.glyphs:
                            state.glyphs.append(replace(
                                glyph,
                                baseline_y_mm=baseline,
                                line_index=global_line,
                                glyph_index=len(state.glyphs),
                            ))
                        state.cursor_y = line_top + source_line.advance_mm
                        state.line_count += 1
                        if source_line.glyphs:
                            state.line_boxes.append(RectMM(
                                source_line.used_left_mm,
                                line_top,
                                source_line.used_right_mm - source_line.used_left_mm,
                                source_line.advance_mm,
                            ))
                    paragraph_records.append({
                        "paragraph_id": f"{element.id}-paragraph-{paragraph_index + 1:03d}",
                        "source_element_id": element.id,
                        "source_page_index": element.source_page_index,
                        "target_page_start": first_page_index,
                        "target_page_end": len(pages),
                        "content_left_mm": round(left, 6),
                        "paragraph_left_mm": round(flowed.lines[-1].left_mm, 6),
                        "first_line_left_mm": round(first_line_left, 6),
                        "paragraph_right_mm": round(flowed.lines[0].right_mm, 6),
                        "baseline_mm": round(
                            state.cursor_y - flowed.lines[-1].advance_mm
                            + font.metrics.ascent * scale * flowed.font_scale,
                            6,
                        ),
                        "semantic_role": paragraph_model.semantic_role or "body",
                        "alignment": paragraph_model.alignment or "left",
                        "left_indent_mm": paragraph_model.left_indent_mm or 0.0,
                        "right_indent_mm": paragraph_model.right_indent_mm or 0.0,
                        "first_line_indent_mm": paragraph_model.first_line_indent_mm or 0.0,
                        "hanging_indent_mm": paragraph_model.hanging_indent_mm or 0.0,
                        "tab_stops_mm": [round(value, 6) for value in flowed.tab_stops_mm],
                        "line_count": len(flowed.lines),
                        "font_scale": round(flowed.font_scale, 6),
                    })
                    if paragraph_model.runs:
                        decorations = build_underlines(
                            paragraph_model,
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
                    effective_after = (
                        flowed.space_after_mm
                        if paragraph_model.space_after_mm is not None
                        else paragraph_spacing
                    )
                    if state.cursor_y + effective_after <= content_bottom + 1e-9:
                        state.cursor_y += effective_after
                    record_trace(
                        element, "text", cursor_before, "normal_flow", zones_before,
                    )
                element_formulas = [
                    formula for formula in rendered_formulas
                    if formula.element_id.startswith(f"{element.id}-formula-")
                ]
                details[element.id] = {
                    "type": "text",
                    "characters": sum(map(len, element.paragraphs)),
                    "formulas": [asdict(formula) for formula in element_formulas],
                    "paragraphs": [
                        item for item in paragraph_records
                        if item["source_element_id"] == element.id
                    ],
                }
                continue

            if isinstance(element, SourceTableElement):
                if state.has_content:
                    state.cursor_y += spacing_before
                table_count += 1
                table_cells += len(element.cells)
                table_plan = plan_table_layout(
                    element,
                    font,
                    available_width_mm=usable_width,
                    page_scale=page_transform.scale,
                    size_options=size_options,
                    paragraph_options=paragraph_config,
                    table_options=table_config,
                )
                state.warnings.extend(table_plan.warnings)
                table_x, table_affinity = _table_x(
                    element,
                    table_plan.width_mm,
                    content_rect,
                    page_transform,
                )
                mapped_table = _mapped_element_rect(element.bbox, page_transform)
                if (
                    document_layout_mode == "preserve"
                    and mapped_table is not None
                    and not state.has_content
                ):
                    state.cursor_y = max(top, mapped_table.y)
                next_row = 0
                fragment_index = 0
                while next_row < element.rows:
                    available = content_bottom - state.cursor_y
                    headers = (
                        list(range(element.repeat_header_rows))
                        if next_row > 0 and element.repeat_header_rows
                        else []
                    )
                    header_height = sum(
                        table_plan.row_heights_mm[row] for row in headers
                    )
                    selected = list(headers)
                    used_height = header_height
                    candidate = next_row
                    while candidate < element.rows:
                        group_end = protected_row_end(element, candidate)
                        group_rows = list(range(candidate, group_end))
                        group_height = sum(
                            table_plan.row_heights_mm[row] for row in group_rows
                        )
                        if selected and used_height + group_height > available + 1e-9:
                            break
                        if not selected and group_height > available + 1e-9:
                            break
                        selected.extend(group_rows)
                        used_height += group_height
                        candidate = group_end
                    data_rows = [row for row in selected if row >= next_row]
                    if not data_rows:
                        if not enabled:
                            raise ValueError(OVERFLOW_ERROR)
                        full_available = content_bottom - top
                        group_end = protected_row_end(element, next_row)
                        group_height = sum(
                            table_plan.row_heights_mm[row]
                            for row in range(next_row, group_end)
                        )
                        if state.has_content or state.cursor_y > top + 1e-9:
                            finish_page()
                            continue
                        if header_height + group_height > full_available + 1e-9:
                            state.warnings.append(
                                f"table_row_span_group_taller_than_page:{element.id}:{next_row}"
                            )
                            selected = headers + list(range(next_row, group_end))
                            data_rows = list(range(next_row, group_end))
                        else:
                            finish_page()
                            continue
                    fragment = layout_table_fragment(
                        element,
                        selected,
                        font,
                        x=table_x,
                        y=state.cursor_y,
                        size_options=dict(size_options),
                        paragraph_options=paragraph_config,
                        table_options=table_config,
                        page_scale=page_transform.scale,
                        plan=table_plan,
                    )
                    if fragment_index > 0:
                        table_splits += 1
                    repeated_headers_emitted += len(headers)
                    shared_borders_suppressed += fragment.shared_borders_suppressed
                    state.warnings.extend(fragment.warnings)
                    fragment_top = state.cursor_y
                    for glyph in fragment.glyphs:
                        state.glyphs.append(replace(
                            glyph, glyph_index=len(state.glyphs),
                            line_index=state.line_count + glyph.line_index,
                        ))
                    for stroke in fragment.strokes:
                        state.graphics.append(replace(stroke, id=len(state.graphics)))
                    state.line_count += max(1, len(selected))
                    state.cursor_y += fragment.height_mm + spacing_after
                    if state.cursor_y > content_bottom + spacing_after + 1e-9:
                        state.warnings.append(f"table_fragment_overflow:{element.id}")
                    add_source_id(element.id)
                    fragment_index += 1
                    target_table = RectMM(
                        table_x, fragment_top, table_plan.width_mm, fragment.height_mm
                    )
                    placement = {
                        "id": element.id,
                        "type": "semantic-table",
                        "source_page_index": element.source_page_index,
                        "target_page_index": len(pages),
                        "source_bbox_mm": (
                            {
                                "x": element.bbox.x0,
                                "y": element.bbox.y0,
                                "width": element.bbox.width,
                                "height": element.bbox.height,
                            }
                            if element.bbox is not None else None
                        ),
                        "mapped_bbox_mm": rect_payload(mapped_table),
                        "output_bbox_mm": rect_payload(target_table),
                        "scale": round(table_plan.scale, 6),
                        "page_scale": round(page_transform.scale, 6),
                        "placement_mode": document_layout_mode,
                        "anchor_affinity": table_affinity,
                    }
                    state.placements.append(placement)
                    placement_records.append(placement)
                    state.table_fragments.append({
                        "table_id": element.id,
                        "rows": selected,
                        "row_heights_mm": list(fragment.row_heights_mm),
                        "column_widths_mm": list(table_plan.column_widths_mm),
                        "continued_from_previous": next_row > 0,
                        "continues_next": data_rows[-1] < element.rows - 1,
                        "border_strokes": fragment.border_count,
                        "target_bbox": rect_payload(target_table),
                    })
                    table_pages.add((element.id, len(pages)))
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
                    "source_width_mm": element.preferred_width_mm
                    or sum(element.column_widths_mm),
                    "target_width_mm": table_plan.width_mm,
                    "scale": table_plan.scale,
                    "column_widths_mm": list(table_plan.column_widths_mm),
                    "row_heights_mm": list(table_plan.row_heights_mm),
                    "auto_height_rows": table_plan.auto_height_rows,
                    "warnings": list(table_plan.warnings),
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
                source_strokes = [
                    replace(
                        stroke,
                        points=[
                            Point(
                                page_transform.scale_length(point.x),
                                page_transform.scale_length(point.y),
                            )
                            for point in stroke.points
                        ],
                    )
                    for stroke in source_strokes
                ]
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
                cursor_before = state.cursor_y
                zones_before = _zone_payloads(state.exclusion_zones)
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
                    timing = (
                        stage_timings.measure("latex_render")
                        if stage_timings else nullcontext()
                    )
                    with timing:
                        rendered_visual = (
                            render_visual_math_image(
                                element.visual_image_path,
                                element.expression,
                                element.visual_ppmm
                                or float(latex_config.get("render_ppmm", 24.0)),
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
                            expression_model=element.model,
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
                formula_target = (
                    _payload_rect(placed_infos[0].target_bbox) if placed_infos else None
                )
                record_trace(
                    element, "math", cursor_before, "configured_block_spacing",
                    zones_before, target_bbox=formula_target,
                )
                continue

            if isinstance(element, SourceRasterImageElement):
                cursor_before = state.cursor_y
                zones_before = _zone_payloads(state.exclusion_zones)
                image_found += 1
                if image_mode == "off":
                    warnings.append(f"image_skipped_images_off: {element.id}")
                    details[element.id] = {"type": "raster-image", "mode": "off", "skipped": True}
                    continue
                display_width, display_height = _image_size(
                    element, usable_width, content_bottom - top,
                    default_width_ratio, max_height_ratio,
                    page_transform.scale,
                )
                width, height = _rotated_size(
                    display_width, display_height, element.rotation_deg
                )
                paragraph_relative = (
                    document_layout_mode == "hybrid"
                    and element.wrap_mode != "inline"
                    and element.anchor_type != "flow"
                    and element.relative_to_v not in {"page", "margin"}
                )
                if (
                    paragraph_relative
                    and state.cursor_y + required_before + height > content_bottom + 1e-9
                ):
                    if not enabled:
                        raise ValueError(OVERFLOW_ERROR)
                    finish_page()
                    cursor_before = state.cursor_y
                    zones_before = _zone_payloads(state.exclusion_zones)
                    required_before = 0.0
                mapped = _mapped_element_rect(element.bbox, page_transform)
                if (
                    document_layout_mode == "hybrid"
                    and mapped is not None
                    and element.relative_to_v not in {"page", "margin"}
                ):
                    mapped = RectMM(
                        mapped.x,
                        state.cursor_y + required_before + element.anchor_offset_y_mm,
                        width,
                        height,
                    )
                was_preplaced = element.id in preplacements
                zone_was_active = False
                if was_preplaced:
                    prepared_placement = preplacements[element.id]
                    zone_was_active = prepared_placement.active
                    prepared_placement.active = True
                    output_rect = prepared_placement.target_rect
                    mapped = prepared_placement.mapped_rect
                    effective_wrap = prepared_placement.wrap_mode
                    placement_warnings = prepared_placement.warnings
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
                timing = (
                    stage_timings.measure("image_vectorization")
                    if stage_timings else nullcontext()
                )
                with timing:
                    prepared = preprocess_image(
                        element.image_path, image_options, debug_path=debug_path
                    )
                    vectorized = vectorize_image(
                        prepared,
                        image_options,
                        mode=image_mode,
                        width_mm=display_width,
                        height_mm=display_height,
                        element_id=element.id,
                        source_path=str(element.image_path),
                    )
                for stroke in vectorized.strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics),
                        points=[
                            _rotate_image_point(
                                point,
                                output_rect,
                                display_width,
                                display_height,
                                element.rotation_deg,
                            )
                            for point in stroke.points
                        ],
                    ))
                if document_layout_mode == "reflow" or element.wrap_mode == "inline":
                    state.cursor_y += output_rect.height + spacing_after
                elif effective_wrap == "top_bottom":
                    state.cursor_y = max(state.cursor_y, output_rect.bottom + spacing_after)
                elif effective_wrap == "square" and not zone_was_active:
                    padding_default = _scaled_padding(
                        float(hybrid_config.get("image_padding_mm", 2.0)),
                        page_transform.scale,
                        image_options,
                    )
                    state.exclusion_zones.append(ExclusionZone(
                        output_rect,
                        element.wrap_side,
                        element.id,
                        _scaled_padding(
                            element.distance_left_mm, page_transform.scale, image_options
                        ) or padding_default,
                        _scaled_padding(
                            element.distance_right_mm, page_transform.scale, image_options
                        ) or padding_default,
                        _scaled_padding(
                            element.distance_top_mm, page_transform.scale, image_options
                        ),
                        _scaled_padding(
                            element.distance_bottom_mm, page_transform.scale, image_options
                        ),
                    ))
                add_source_id(element.id)
                image_vectorized += int(bool(vectorized.strokes))
                image_cache_hits += int(vectorized.cache_hit)
                image_cache_misses += int(not vectorized.cache_hit)
                image_strokes += len(vectorized.strokes)
                image_points += vectorized.point_count
                image_micro_strokes_suppressed += vectorized.micro_strokes_suppressed
                state.warnings.extend(f"{warning}: {element.id}" for warning in vectorized.warnings)
                placement = _placement_record(
                    element.id,
                    element.source_order,
                    element.source_page_index,
                    len(pages),
                    element.bbox,
                    mapped,
                    output_rect,
                    element.anchor_type,
                    effective_wrap,
                    element.wrap_side,
                    element.displayed_width,
                    placement_warnings,
                    "raster-image",
                    "page_anchor_preplaced" if zone_was_active else "activated_at_source_order",
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
                record_trace(
                    element,
                    "image",
                    cursor_before,
                    "page_anchor_preplaced" if zone_was_active else "activated_at_source_order",
                    zones_before, target_bbox=output_rect,
                )
                continue

            if isinstance(element, SourceVectorElement):
                cursor_before = state.cursor_y
                zones_before = _zone_payloads(state.exclusion_zones)
                vector_count += 1
                width, height = _vector_size(
                    element, usable_width, content_bottom - top, page_transform.scale
                )
                mapped = _mapped_element_rect(element.bbox, page_transform)
                was_preplaced = element.id in preplacements
                zone_was_active = False
                if was_preplaced:
                    prepared_placement = preplacements[element.id]
                    zone_was_active = prepared_placement.active
                    prepared_placement.active = True
                    output_rect = prepared_placement.target_rect
                    mapped = prepared_placement.mapped_rect
                    effective_wrap = prepared_placement.wrap_mode
                    placement_warnings = prepared_placement.warnings
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
                elif effective_wrap == "square" and not zone_was_active:
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
                    element.source_order,
                    element.source_page_index,
                    len(pages),
                    element.bbox,
                    mapped,
                    output_rect,
                    element.anchor_type,
                    effective_wrap,
                    element.wrap_side,
                    width,
                    placement_warnings,
                    "pdf-vector",
                    "page_anchor_preplaced" if zone_was_active else "activated_at_source_order",
                )
                state.placements.append(placement)
                placement_records.append(placement)
                details[element.id] = {
                    "type": "pdf-vector",
                    "strokes": len(element.strokes),
                    **placement,
                }
                record_trace(
                    element,
                    "image",
                    cursor_before,
                    "page_anchor_preplaced" if zone_was_active else "activated_at_source_order",
                    zones_before, target_bbox=output_rect,
                )

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
        "image_cache_hits": image_cache_hits,
        "image_cache_misses": image_cache_misses,
        "image_micro_strokes_suppressed": image_micro_strokes_suppressed,
        "underlines": underline_count,
        "generic_lines": line_count_semantic,
        "arrows": arrow_count,
        "tables": table_count,
        "table_cells": table_cells,
        "table_pages": len(table_pages),
        "table_splits": table_splits,
        "repeated_headers_emitted": repeated_headers_emitted,
        "shared_borders_suppressed": shared_borders_suppressed,
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
        "cache_hits": renderer.cache_hits if renderer is not None else 0,
        "cache_misses": renderer.cache_misses if renderer is not None else 0,
        "glyph_cache_hits": renderer.glyph_cache_hits if renderer is not None else 0,
        "glyph_cache_misses": renderer.glyph_cache_misses if renderer is not None else 0,
        "glyph_cache_version": renderer.glyph_cache_version if renderer is not None else None,
        "vector_rendered": renderer.vector_renders if renderer is not None else 0,
        "raster_fallback": renderer.raster_fallbacks if renderer is not None else 0,
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
        trace_records,
        line_advance,
    )
    layout_stats["page_transform"] = (
        page_transform_records[0] if len(page_transform_records) == 1 else page_transform_records
    )
    layout_stats["layout_objects"] = {
        "images_scaled": len({
            str(item["id"])
            for item in placement_records
            if item.get("element_type") in {"raster-image", "pdf-vector"}
            and abs(float(item.get("scale", 1.0)) - 1.0) > 1e-9
        }),
        "tables_scaled": len({
            str(item["id"])
            for item in placement_records
            if item.get("type") == "semantic-table"
            and abs(float(item.get("scale", 1.0)) - 1.0) > 1e-9
        }),
        "tables_paginated": sum(
            detail.get("type") == "table" and int(detail.get("pages", 1)) > 1
            for detail in details.values()
        ),
        "table_rows_auto_height": sum(
            int(detail.get("auto_height_rows", 0)) for detail in details.values()
        ),
        "object_overflow_count": sum(
            "overflow" in warning for warning in [*warnings, *state.warnings]
        ),
    }
    if layout_debug_dir is not None:
        export_layout_debug(
            layout_debug_dir,
            page,
            placement_records,
            all_line_boxes,
            trace_records=trace_records,
            content_rect=content_rect,
            paragraph_records=paragraph_records,
            page_transforms=page_transform_records,
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
    default_width_ratio: float, max_height_ratio: float, page_scale: float = 1.0,
) -> tuple[float, float]:
    aspect = element.width_px / max(1, element.height_px)
    if element.displayed_width is not None:
        width = element.displayed_width * page_scale
        height = width / max(aspect, 1e-9)
    elif element.displayed_height is not None:
        height = element.displayed_height * page_scale
        width = height * aspect
    else:
        width = usable_width * default_width_ratio
        height = width / max(aspect, 1e-9)
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
    element: SourceVectorElement,
    usable_width: float,
    usable_height: float,
    page_scale: float = 1.0,
) -> tuple[float, float]:
    points = [point for stroke in element.strokes for point in stroke.points]
    width = max(point.x for point in points) - min(point.x for point in points)
    height = max(point.y for point in points) - min(point.y for point in points)
    scale = min(
        page_scale,
        usable_width / max(width, 1e-9),
        usable_height * 0.6 / max(height, 1e-9),
    )
    return max(width * scale, 0.1), max(height * scale, 0.1)


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid mapping field: pagination.{key}")
    return value


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
    transform: PageTransform,
) -> RectMM | None:
    if bbox is None:
        return None
    source_rect = RectMM(bbox.x0, bbox.y0, bbox.width, bbox.height)
    return transform.map_rect(source_rect)


def _table_x(
    table: SourceTableElement,
    width: float,
    content: RectMM,
    transform: PageTransform,
) -> tuple[float, str]:
    alignment = table.alignment
    if alignment is None and table.bbox is not None:
        source_center = table.bbox.x0 + table.bbox.width / 2
        relative = (
            source_center - transform.source_content_rect.x
        ) / transform.source_content_rect.width
        alignment = "left" if relative < 0.4 else "right" if relative > 0.6 else "center"
    alignment = alignment or "left"
    if alignment == "right":
        x = content.right - width
    elif alignment == "center":
        x = content.x + (content.width - width) / 2
    else:
        x = content.x + transform.scale_length(table.left_indent_mm or 0.0)
    return min(content.right - width, max(content.x, x)), alignment
