from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pymupdf
from PIL import Image, UnidentifiedImageError

from plotter_processor.document_models import (
    SourceBBox,
    SourceDocument,
    SourcePage,
    SourceRasterImageElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.models import PlotterStroke, Point

PT_TO_MM = 25.4 / 72.0


def read_pdf_document(path: Path, assets_dir: Path) -> SourceDocument:
    try:
        document = pymupdf.open(path)
    except Exception as error:
        raise ValueError(f"Cannot read PDF document: {path}") from error
    pages: list[SourcePage] = []
    warnings: list[str] = []
    blob_paths: dict[str, Path] = {}
    try:
        for page_index, page in enumerate(document):
            page_dir = assets_dir / f"page-{page_index + 1:03d}"
            elements: list[SourceTextElement | SourceRasterImageElement | SourceVectorElement] = []
            order = 0
            blocks = page.get_text("dict", sort=False).get("blocks", [])
            ordered_blocks = sorted(
                enumerate(blocks),
                key=lambda item: (
                    round(float(item[1].get("bbox", (0, 0, 0, 0))[1]), 3),
                    round(float(item[1].get("bbox", (0, 0, 0, 0))[0]), 3),
                    item[0],
                ),
            )
            for _, block in ordered_blocks:
                bbox = _bbox(block.get("bbox"))
                if block.get("type") == 0:
                    paragraphs = tuple(
                        "".join(span.get("text", "") for span in line.get("spans", []))
                        for line in block.get("lines", [])
                    )
                    if any(item.strip() for item in paragraphs):
                        elements.append(
                            SourceTextElement(
                                f"page-{page_index + 1:03d}-text-{order + 1:03d}",
                                order,
                                page_index,
                                paragraphs,
                                bbox,
                            )
                        )
                        order += 1
                elif block.get("type") == 1 and block.get("image"):
                    blob = bytes(block["image"])
                    digest = hashlib.sha256(blob).hexdigest()[:12]
                    if digest not in blob_paths:
                        page_dir.mkdir(parents=True, exist_ok=True)
                        asset = page_dir / f"image-{len(blob_paths) + 1:03d}-{digest}.png"
                        try:
                            with Image.open(__import__("io").BytesIO(blob)) as image:
                                image.save(asset, format="PNG")
                        except (OSError, UnidentifiedImageError) as error:
                            warnings.append(f"pdf_image_decode_failed: page {page_index + 1}: {error}")
                            continue
                        blob_paths[digest] = asset
                    asset = blob_paths[digest]
                    with Image.open(asset) as image:
                        width_px, height_px = image.size
                    elements.append(
                        SourceRasterImageElement(
                            f"page-{page_index + 1:03d}-image-{order + 1:03d}",
                            order,
                            page_index,
                            asset,
                            width_px,
                            height_px,
                            bbox.width * PT_TO_MM if bbox else None,
                            bbox.height * PT_TO_MM if bbox else None,
                            bbox,
                        )
                    )
                    order += 1

            for drawing_index, drawing in enumerate(page.get_drawings()):
                if _drawing_requires_raster(drawing):
                    rect = drawing.get("rect")
                    if rect is None or rect.is_empty:
                        warnings.append(
                            f"pdf_complex_drawing_skipped: page {page_index + 1}, "
                            f"drawing {drawing_index + 1}"
                        )
                        continue
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=rect, alpha=True)
                    blob = pixmap.tobytes("png")
                    digest = hashlib.sha256(blob).hexdigest()[:12]
                    if digest not in blob_paths:
                        page_dir.mkdir(parents=True, exist_ok=True)
                        asset = page_dir / f"image-{len(blob_paths) + 1:03d}-{digest}.png"
                        asset.write_bytes(blob)
                        blob_paths[digest] = asset
                    bbox = _bbox(rect)
                    elements.append(
                        SourceRasterImageElement(
                            f"page-{page_index + 1:03d}-image-{order + 1:03d}",
                            order,
                            page_index,
                            blob_paths[digest],
                            pixmap.width,
                            pixmap.height,
                            bbox.width * PT_TO_MM if bbox else None,
                            bbox.height * PT_TO_MM if bbox else None,
                            bbox,
                        )
                    )
                    warnings.append(
                        f"pdf_complex_drawing_rasterized: page {page_index + 1}, "
                        f"drawing {drawing_index + 1}"
                    )
                    order += 1
                    continue
                drawing_elements, drawing_warnings = _convert_drawing(
                    drawing, page_index, order, drawing_index
                )
                warnings.extend(drawing_warnings)
                elements.extend(drawing_elements)
                order += len(drawing_elements)
            elements, overlap_warnings = _omit_raster_frames(elements)
            warnings.extend(overlap_warnings)
            elements.sort(key=lambda item: (
                round(item.bbox.y0, 3) if item.bbox else math.inf,
                round(item.bbox.x0, 3) if item.bbox else math.inf,
                item.source_order,
            ))
            elements = [_with_order(element, index) for index, element in enumerate(elements)]
            pages.append(SourcePage(page_index, page.rect.width, page.rect.height, tuple(elements)))
    finally:
        document.close()
    return SourceDocument(path, tuple(pages), tuple(dict.fromkeys(warnings)))


def _convert_drawing(
    drawing: dict[str, object], page_index: int, order: int, drawing_index: int
) -> tuple[list[SourceVectorElement], list[str]]:
    warnings: list[str] = []
    strokes: list[PlotterStroke] = []
    for item in drawing.get("items", []):
        kind = item[0]
        points: list[Point] = []
        closed = False
        segment = "pdf-line"
        if kind == "l":
            points = [_point(item[1]), _point(item[2])]
        elif kind == "re":
            rect = item[1]
            points = [
                Point(rect.x0 * PT_TO_MM, rect.y0 * PT_TO_MM),
                Point(rect.x1 * PT_TO_MM, rect.y0 * PT_TO_MM),
                Point(rect.x1 * PT_TO_MM, rect.y1 * PT_TO_MM),
                Point(rect.x0 * PT_TO_MM, rect.y1 * PT_TO_MM),
            ]
            closed = True
            segment = "pdf-rectangle"
        elif kind == "qu":
            quad = item[1]
            points = [_point(point) for point in (quad.ul, quad.ur, quad.lr, quad.ll)]
            closed = True
            segment = "pdf-polyline"
        elif kind == "c":
            raw = [_point(value) for value in item[1:5]]
            points = _flatten_cubic(*raw)
            segment = "pdf-bezier"
        else:
            warnings.append(
                f"pdf_drawing_item_not_supported: page {page_index + 1}, type {kind}"
            )
            continue
        if len({(point.x, point.y) for point in points}) >= 2:
            strokes.append(
                PlotterStroke(
                    len(strokes), points, closed, segment_types=(segment,)
                )
            )
    if not strokes:
        return [], warnings
    bbox = _bbox(drawing.get("rect"))
    element_id = f"page-{page_index + 1:03d}-vector-{drawing_index + 1:03d}"
    for stroke in strokes:
        stroke.element_id = element_id
        stroke.element_type = "pdf-vector"
    return [SourceVectorElement(element_id, order, page_index, tuple(strokes), bbox)], warnings


def _bbox(value: object) -> SourceBBox | None:
    if value is None:
        return None
    try:
        x0, y0, x1, y1 = (float(part) for part in value)
    except (TypeError, ValueError):
        x0, y0, x1, y1 = float(value.x0), float(value.y0), float(value.x1), float(value.y1)
    return SourceBBox(x0, y0, x1, y1)


def _point(value: object) -> Point:
    return Point(float(value.x) * PT_TO_MM, float(value.y) * PT_TO_MM)


def _flatten_cubic(p0: Point, p1: Point, p2: Point, p3: Point) -> list[Point]:
    points: list[Point] = []
    for index in range(17):
        t = index / 16
        u = 1 - t
        points.append(Point(
            u**3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t**3 * p3.x,
            u**3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t**3 * p3.y,
        ))
    return points


def _drawing_requires_raster(drawing: dict[str, object]) -> bool:
    return (
        drawing.get("fill") is not None
        or drawing.get("fill_opacity", 1.0) not in {None, 1.0}
        or drawing.get("stroke_opacity", 1.0) not in {None, 1.0}
    )


def _omit_raster_frames(
    elements: list[SourceTextElement | SourceRasterImageElement | SourceVectorElement],
) -> tuple[
    list[SourceTextElement | SourceRasterImageElement | SourceVectorElement], list[str]
]:
    rasters = [item for item in elements if isinstance(item, SourceRasterImageElement)]
    kept: list[SourceTextElement | SourceRasterImageElement | SourceVectorElement] = []
    warnings: list[str] = []
    for element in elements:
        is_rectangle_frame = (
            isinstance(element, SourceVectorElement)
            and element.bbox is not None
            and element.strokes
            and all(stroke.segment_types == ("pdf-rectangle",) for stroke in element.strokes)
        )
        if is_rectangle_frame and any(
            raster.bbox is not None and _coverage(element.bbox, raster.bbox) >= 0.85
            for raster in rasters
        ):
            warnings.append(f"pdf_raster_frame_omitted_in_reflow: {element.id}")
            continue
        kept.append(element)
    return kept, warnings


def _coverage(frame: SourceBBox, content: SourceBBox) -> float:
    intersection_width = max(0.0, min(frame.x1, content.x1) - max(frame.x0, content.x0))
    intersection_height = max(0.0, min(frame.y1, content.y1) - max(frame.y0, content.y0))
    content_area = content.width * content.height
    return intersection_width * intersection_height / content_area if content_area else 0.0


def _with_order(element: object, order: int):
    from dataclasses import replace

    return replace(element, source_order=order)
