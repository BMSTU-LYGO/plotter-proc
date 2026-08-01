from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from plotter_processor.document_models import (
    SourceDocument,
    SourceRasterImageElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.font_loader import LoadedFont
from plotter_processor.image_preprocessor import preprocess_image
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.models import LayoutResult, PageSpec, PlotterStroke, Point, PositionedGlyph
from plotter_processor.text_normalizer import normalize_text
from plotter_processor.vector_layout import OVERFLOW_ERROR, layout_text


@dataclass(slots=True)
class StructuredLayout:
    layout: LayoutResult
    graphic_strokes: list[PlotterStroke]
    warnings: list[str]
    import_statistics: dict[str, object]
    element_details: dict[str, dict[str, object]]


def layout_structured_document(
    document: SourceDocument,
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    size_options: Mapping[str, object],
    image_options: Mapping[str, object],
    *,
    image_mode: str,
    image_debug_dir: Path | None,
    tab_spaces: int,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> StructuredLayout:
    left = float(margins["left"])
    right = float(margins["right"])
    top = float(margins["top"])
    bottom = page.height_mm - float(margins["bottom"])
    usable_width = page.width_mm - left - right
    cursor_y = top
    spacing_before = float(image_options.get("spacing_before_mm", 2.0))
    spacing_after = float(image_options.get("spacing_after_mm", 2.0))
    default_width_ratio = float(image_options.get("default_width_ratio", 0.75))
    max_height_ratio = float(image_options.get("max_height_ratio", 0.60))
    glyphs: list[PositionedGlyph] = []
    graphics: list[PlotterStroke] = []
    warnings = list(document.warnings)
    details: dict[str, dict[str, object]] = {}
    line_offset = 0
    characters = 0
    max_width = 0.0
    image_found = image_vectorized = image_strokes = image_points = vector_count = 0

    for page_source in document.pages:
        for element in page_source.elements:
            if isinstance(element, SourceTextElement):
                normalized_paragraphs: list[str] = []
                for paragraph in element.paragraphs:
                    normalized, normalization_warnings = normalize_text(paragraph)
                    normalized_paragraphs.extend(normalized.split("\n"))
                    warnings.extend(normalization_warnings)
                if not any(normalized_paragraphs):
                    cursor_y += float(size_options.get("paragraph_spacing_mm", 0.0))
                    continue
                local_margins = dict(margins)
                local_margins["top"] = cursor_y
                result = layout_text(
                    normalized_paragraphs, font, page, local_margins, size_options,
                    tab_spaces=tab_spaces, engine=engine, language=language, script=script,
                    direction=direction, features=features,
                )
                for glyph in result.glyphs:
                    glyphs.append(replace(
                        glyph,
                        glyph_index=len(glyphs),
                        line_index=glyph.line_index + line_offset,
                    ))
                line_offset += result.line_count
                characters += result.character_count
                max_width = max(max_width, result.used_width_mm)
                cursor_y += result.used_height_mm + float(size_options.get("paragraph_spacing_mm", 0.0))
                warnings.extend(result.warnings)
                details[element.id] = {"type": "text", "characters": result.character_count}
                continue

            cursor_y += spacing_before
            if isinstance(element, SourceRasterImageElement):
                image_found += 1
                if image_mode == "off":
                    warnings.append(f"image_skipped_images_off: {element.id}")
                    details[element.id] = {"type": "raster-image", "mode": "off", "skipped": True}
                    cursor_y += spacing_after
                    continue
                width, height = _image_size(
                    element, usable_width, bottom - top, default_width_ratio, max_height_ratio
                )
                if cursor_y + height > bottom + 1e-9:
                    raise ValueError(OVERFLOW_ERROR)
                debug_path = (
                    image_debug_dir / f"{element.id}.png" if image_debug_dir is not None else None
                )
                preprocessed = preprocess_image(element.image_path, image_options, debug_path=debug_path)
                vectorized = vectorize_image(
                    preprocessed, image_options, mode=image_mode, width_mm=width, height_mm=height,
                    element_id=element.id, source_path=str(element.image_path),
                )
                x = left + (usable_width - width) / 2
                for stroke in vectorized.strokes:
                    graphics.append(replace(
                        stroke,
                        id=len(graphics),
                        points=[Point(point.x + x, point.y + cursor_y) for point in stroke.points],
                    ))
                image_vectorized += int(bool(vectorized.strokes))
                image_strokes += len(vectorized.strokes)
                image_points += vectorized.point_count
                warnings.extend(f"{warning}: {element.id}" for warning in vectorized.warnings)
                details[element.id] = {
                    "type": "raster-image", "mode": vectorized.mode,
                    "width_mm": round(width, 4), "height_mm": round(height, 4),
                    "strokes": len(vectorized.strokes), "points": vectorized.point_count,
                }
                cursor_y += height + spacing_after
                continue

            if isinstance(element, SourceVectorElement):
                vector_count += 1
                width, height = _vector_size(element, usable_width, bottom - top)
                if cursor_y + height > bottom + 1e-9:
                    raise ValueError(OVERFLOW_ERROR)
                source_points = [point for stroke in element.strokes for point in stroke.points]
                min_x = min(point.x for point in source_points)
                min_y = min(point.y for point in source_points)
                source_width = max(point.x for point in source_points) - min_x
                source_height = max(point.y for point in source_points) - min_y
                scale = min(width / max(source_width, 1e-9), height / max(source_height, 1e-9))
                x = left + (usable_width - source_width * scale) / 2
                for stroke in element.strokes:
                    graphics.append(replace(
                        stroke, id=len(graphics), element_id=element.id, element_type="pdf-vector",
                        points=[Point(x + (p.x - min_x) * scale, cursor_y + (p.y - min_y) * scale) for p in stroke.points],
                    ))
                details[element.id] = {"type": "pdf-vector", "strokes": len(element.strokes)}
                cursor_y += source_height * scale + spacing_after

    if not glyphs and not graphics:
        raise ValueError("Document contains no drawable text or images")
    layout = LayoutResult(
        glyphs, list(dict.fromkeys(warnings)), line_offset, characters, max_width,
        max(0.0, cursor_y - top),
    )
    stats = {
        "source_pages": len(document.pages),
        "text_elements": sum(isinstance(item, SourceTextElement) for item in document.elements),
        "raster_images_found": image_found,
        "raster_images_vectorized": image_vectorized,
        "pdf_vector_elements": vector_count,
        "images_skipped": image_found - image_vectorized,
        "image_strokes": image_strokes,
        "image_points": image_points,
    }
    return StructuredLayout(layout, graphics, list(dict.fromkeys(warnings)), stats, details)


def save_document_structure(
    document: SourceDocument,
    path: Path,
    *,
    details: Mapping[str, Mapping[str, object]] | None = None,
    layout_mode: str = "reflow",
) -> None:
    details = details or {}
    payload = {
        "source": str(document.source_path),
        "layout_mode": layout_mode,
        "warnings": list(document.warnings),
        "pages": [
            {
                "source_page_index": page.source_page_index,
                "width_pt": page.width_pt,
                "height_pt": page.height_pt,
                "elements": [
                    {
                        "id": element.id,
                        "source_order": element.source_order,
                        "type": _element_type(element),
                        "bbox": _bbox_payload(element.bbox),
                        **(
                            {"paragraphs": list(element.paragraphs)}
                            if isinstance(element, SourceTextElement)
                            else {}
                        ),
                        **(
                            {
                                "asset_path": str(element.image_path),
                                "width_px": element.width_px,
                                "height_px": element.height_px,
                                "displayed_width": element.displayed_width,
                                "displayed_height": element.displayed_height,
                            }
                            if isinstance(element, SourceRasterImageElement)
                            else {}
                        ),
                        **dict(details.get(element.id, {})),
                    }
                    for element in page.elements
                ],
            }
            for page in document.pages
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _image_size(
    element: SourceRasterImageElement,
    usable_width: float,
    usable_height: float,
    default_width_ratio: float,
    max_height_ratio: float,
) -> tuple[float, float]:
    width = element.displayed_width or usable_width * default_width_ratio
    height = element.displayed_height or width * element.height_px / max(1, element.width_px)
    scale = min(1.0, usable_width / width, usable_height * max_height_ratio / height)
    return width * scale, height * scale


def _vector_size(
    element: SourceVectorElement, usable_width: float, usable_height: float
) -> tuple[float, float]:
    points = [point for stroke in element.strokes for point in stroke.points]
    width = max(point.x for point in points) - min(point.x for point in points)
    height = max(point.y for point in points) - min(point.y for point in points)
    scale = min(1.0, usable_width / max(width, 1e-9), usable_height * 0.6 / max(height, 1e-9))
    return max(width * scale, 0.1), max(height * scale, 0.1)


def _element_type(element: object) -> str:
    if isinstance(element, SourceTextElement):
        return "text"
    if isinstance(element, SourceRasterImageElement):
        return "raster-image"
    return "pdf-vector"


def _bbox_payload(bbox: object) -> dict[str, float] | None:
    if bbox is None:
        return None
    return {"x0": bbox.x0, "y0": bbox.y0, "x1": bbox.x1, "y1": bbox.y1}
