from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from plotter_processor.document_models import (
    SourceDocument,
    SourceMathElement,
    SourceRasterImageElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.font_loader import LoadedFont
from plotter_processor.image_preprocessor import preprocess_image
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.latex_layout import FormulaInfo, layout_latex_paragraph, layout_math_element
from plotter_processor.latex_parser import contains_latex
from plotter_processor.latex_renderer import math_renderer_from_options, render_visual_math_image
from plotter_processor.models import LayoutResult, PageSpec, PlotterStroke, Point, PositionedGlyph
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
    preserve_source_page_breaks: bool = True,
    tab_spaces: int = 4,
    engine: str = "legacy",
    language: str = "ru",
    script: str = "Cyrl",
    direction: str = "ltr",
    features: tuple[str, ...] = (),
) -> PaginatedLayout:
    left = _number(margins, "left")
    right = _number(margins, "right")
    top = _number(margins, "top")
    bottom_margin = _number(margins, "bottom")
    usable_width = page.width_mm - left - right
    footer = _mapping(pagination_options, "footer")
    footer_reserved = _number(footer, "reserved_height_mm") if footer.get("enabled", True) else 0.0
    content_bottom = page.height_mm - bottom_margin - footer_reserved
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
    formula_index = 0
    rendered_formulas: list[FormulaInfo] = []
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
        pages.append(PageLayout(
            len(pages), layout, state.graphics, tuple(state.source_ids),
            list(dict.fromkeys(state.warnings)),
            {
                "text": "".join(state.text_fragments),
                "formulas": [asdict(formula) for formula in state.formulas],
            },
        ))
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
        for element in source_page.elements:
            if isinstance(element, SourceTextElement):
                normalized_paragraphs: list[str] = []
                for raw_paragraph in element.paragraphs:
                    normalized, normalization_warnings = normalize_text(raw_paragraph)
                    warnings.extend(normalization_warnings)
                    normalized_paragraphs.extend(normalized.split("\n"))
                normalized_paragraphs = _merge_multiline_math_blocks(normalized_paragraphs)
                for paragraph_index, paragraph in enumerate(normalized_paragraphs):
                    if not paragraph:
                        ensure_height(line_advance)
                        state.cursor_y += line_advance
                        state.text_fragments.append("\n")
                        add_source_id(element.id)
                        continue
                    if renderer is not None and contains_latex(paragraph):
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

            required_before = spacing_before if state.has_content else 0.0
            if isinstance(element, SourceMathElement):
                if renderer is None:
                    warning = f"math_element_skipped_latex_off: {element.id}"
                    warnings.append(warning)
                    details[element.id] = {"type": "math", "skipped": True, "warning": warning}
                    continue
                formula_index += 1
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
                ensure_height(required_before + height)
                state.cursor_y += required_before
                debug_path = image_debug_dir / f"{element.id}.png" if image_debug_dir else None
                prepared = preprocess_image(element.image_path, image_options, debug_path=debug_path)
                vectorized = vectorize_image(
                    prepared, image_options, mode=image_mode, width_mm=width, height_mm=height,
                    element_id=element.id, source_path=str(element.image_path),
                )
                x = left + (usable_width - width) / 2
                for stroke in vectorized.strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics),
                        points=[Point(point.x + x, point.y + state.cursor_y) for point in stroke.points],
                    ))
                state.cursor_y += height + spacing_after
                add_source_id(element.id)
                image_vectorized += int(bool(vectorized.strokes))
                image_strokes += len(vectorized.strokes)
                image_points += vectorized.point_count
                state.warnings.extend(f"{warning}: {element.id}" for warning in vectorized.warnings)
                details[element.id] = {
                    "type": "raster-image", "mode": vectorized.mode,
                    "width_mm": round(width, 4), "height_mm": round(height, 4),
                    "strokes": len(vectorized.strokes), "points": vectorized.point_count,
                }
                continue

            if isinstance(element, SourceVectorElement):
                vector_count += 1
                width, height = _vector_size(element, usable_width, content_bottom - top)
                ensure_height(required_before + height)
                state.cursor_y += required_before
                source_points = [point for stroke in element.strokes for point in stroke.points]
                min_x = min(point.x for point in source_points)
                min_y = min(point.y for point in source_points)
                source_width = max(point.x for point in source_points) - min_x
                source_height = max(point.y for point in source_points) - min_y
                vector_scale = min(
                    width / max(source_width, 1e-9), height / max(source_height, 1e-9)
                )
                x = left + (usable_width - source_width * vector_scale) / 2
                for stroke in element.strokes:
                    state.graphics.append(replace(
                        stroke, id=len(state.graphics), element_id=element.id,
                        element_type="pdf-vector",
                        points=[
                            Point(
                                x + (point.x - min_x) * vector_scale,
                                state.cursor_y + (point.y - min_y) * vector_scale,
                            )
                            for point in stroke.points
                        ],
                    ))
                state.cursor_y += source_height * vector_scale + spacing_after
                add_source_id(element.id)
                details[element.id] = {"type": "pdf-vector", "strokes": len(element.strokes)}

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
    return PaginatedLayout(
        pages, list(dict.fromkeys(warnings)), stats, details, latex_stats
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
