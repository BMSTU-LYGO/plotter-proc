from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pymupdf
from PIL import Image, UnidentifiedImageError

from plotter_processor.document_models import (
    SourceArrowElement,
    SourceBBox,
    SourceDocument,
    SourceLineElement,
    SourceMathElement,
    SourcePage,
    SourceParagraph,
    SourcePoint,
    SourceRasterImageElement,
    SourceTableCell,
    SourceTableElement,
    SourceTextElement,
    SourceTextRun,
    SourceTextStyle,
    SourceVectorElement,
)
from plotter_processor.models import PlotterStroke, Point
from plotter_processor.pdf_math_detector import collect_pdf_spans, detect_pdf_math_regions

PT_TO_MM = 25.4 / 72.0


def read_pdf_document(
    path: Path,
    assets_dir: Path,
    *,
    math_mode: str = "off",
    math_options: dict[str, object] | None = None,
    math_debug_dir: Path | None = None,
) -> SourceDocument:
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
            elements: list[
                SourceTextElement
                | SourceRasterImageElement
                | SourceVectorElement
                | SourceMathElement
            ] = []
            order = 0
            blocks = page.get_text("dict", sort=False).get("blocks", [])
            page_font_sizes = [
                float(span.get("size", 0.0))
                for block in blocks
                for line in block.get("lines", [])
                for span in line.get("spans", [])
                if float(span.get("size", 0.0)) > 0
            ]
            body_font_size = (
                sorted(page_font_sizes)[len(page_font_sizes) // 2]
                if page_font_sizes else None
            )
            drawings = page.get_drawings()
            options = math_options or {}
            drawing_rects = [
                (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
                for drawing in drawings
                if (rect := drawing.get("rect")) is not None
            ]
            regions, detector_warnings = detect_pdf_math_regions(
                collect_pdf_spans(blocks),
                drawing_rects,
                mode=math_mode,
                confidence_threshold=float(options.get("confidence_threshold", 0.75)),
                max_region_area_ratio=float(options.get("max_region_area_ratio", 0.35)),
                page_area=float(page.rect.width * page.rect.height),
            )
            warnings.extend(
                f"{warning}:page-{page_index + 1:03d}" for warning in detector_warnings
            )
            absorbed_blocks: set[int] = set()
            absorbed_drawings: set[int] = set()
            render_ppmm = float(options.get("render_ppmm", 24.0))
            padding_mm = float(options.get("bbox_padding_mm", 0.8))
            for region in regions:
                clip = pymupdf.Rect(*region.bbox)
                padding_pt = padding_mm / PT_TO_MM
                clip = pymupdf.Rect(
                    max(page.rect.x0, clip.x0 - padding_pt),
                    max(page.rect.y0, clip.y0 - padding_pt),
                    min(page.rect.x1, clip.x1 + padding_pt),
                    min(page.rect.y1, clip.y1 + padding_pt),
                )
                pixels_per_point = render_ppmm * PT_TO_MM
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(pixels_per_point, pixels_per_point),
                    clip=clip,
                    alpha=False,
                )
                if pixmap.width * pixmap.height > int(options.get("max_render_pixels", 16_000_000)):
                    warnings.append(
                        f"pdf_math_region_complexity_limited:page-{page_index + 1:03d}:{region.id}"
                    )
                    continue
                page_dir.mkdir(parents=True, exist_ok=True)
                asset = page_dir / f"{region.id}.png"
                asset.write_bytes(pixmap.tobytes("png"))
                element_id = f"page-{page_index + 1:03d}-math-{len(elements) + 1:03d}"
                absorbed = (
                    *(f"text-block-{index}" for index in region.block_indices),
                    *(f"drawing-{index}" for index in region.drawing_indices),
                )
                elements.append(SourceMathElement(
                    element_id,
                    order,
                    page_index,
                    region.text,
                    True,
                    "pdf-visual",
                    SourceBBox(
                        clip.x0 * PT_TO_MM,
                        clip.y0 * PT_TO_MM,
                        clip.x1 * PT_TO_MM,
                        clip.y1 * PT_TO_MM,
                    ),
                    asset,
                    render_ppmm,
                    absorbed,
                    region.confidence,
                ))
                absorbed_blocks.update(region.block_indices)
                absorbed_drawings.update(region.drawing_indices)
                order += 1
                if math_debug_dir is not None:
                    math_debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_index = sum(
                        isinstance(item, SourceMathElement) for item in elements
                    )
                    (math_debug_dir / f"formula-{debug_index:03d}-pdf-clip.png").write_bytes(
                        pixmap.tobytes("png")
                    )
                    (math_debug_dir / f"formula-{debug_index:03d}-absorbed-elements.json").write_text(
                        json.dumps(
                            {
                                "formula_id": element_id,
                                "absorbed_text_span_ids": list(region.span_ids),
                                "absorbed_vector_ids": [
                                    f"drawing-{index}" for index in region.drawing_indices
                                ],
                                "bbox": list(region.bbox),
                                "confidence": region.confidence,
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
            table, table_blocks, table_drawings = _detect_pdf_table(
                blocks, drawings, page_index, order
            )
            if table is not None:
                elements.append(table)
                order += 1
                absorbed_blocks.update(table_blocks)
                absorbed_drawings.update(table_drawings)
            arrows, arrow_drawings = _detect_pdf_arrows(
                drawings, page_index, order, absorbed_drawings
            )
            elements.extend(arrows)
            order += len(arrows)
            absorbed_drawings.update(arrow_drawings)
            ordered_blocks = sorted(
                enumerate(blocks),
                key=lambda item: (
                    round(float(item[1].get("bbox", (0, 0, 0, 0))[1]), 3),
                    round(float(item[1].get("bbox", (0, 0, 0, 0))[0]), 3),
                    item[0],
                ),
            )
            for block_index, block in ordered_blocks:
                if block_index in absorbed_blocks:
                    continue
                bbox = _bbox(block.get("bbox"))
                if block.get("type") == 0:
                    styled_paragraphs = tuple(
                        _pdf_paragraph_model(line, page.rect.width, body_font_size)
                        for line in block.get("lines", [])
                    )
                    paragraphs = tuple(item.text for item in styled_paragraphs)
                    if any(item.strip() for item in paragraphs):
                        elements.append(
                            SourceTextElement(
                                f"page-{page_index + 1:03d}-text-{order + 1:03d}",
                                order,
                                page_index,
                                paragraphs,
                                bbox,
                                styled_paragraphs,
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
                            bbox.width if bbox else None,
                            bbox.height if bbox else None,
                            bbox,
                            "absolute",
                            "none",
                        )
                    )
                    order += 1

            for drawing_index, drawing in enumerate(drawings):
                if drawing_index in absorbed_drawings:
                    continue
                line = _single_pdf_line(drawing)
                if line is not None:
                    start, end = line
                    role, confidence = _classify_pdf_line(start, end, blocks)
                    elements.append(SourceLineElement(
                        f"page-{page_index + 1:03d}-line-{drawing_index + 1:03d}",
                        order,
                        page_index,
                        SourcePoint(start.x * PT_TO_MM, start.y * PT_TO_MM),
                        SourcePoint(end.x * PT_TO_MM, end.y * PT_TO_MM),
                        float(drawing.get("width", 1.0)) * PT_TO_MM,
                        None,
                        _bbox(drawing.get("rect")),
                        role,
                        confidence,
                    ))
                    order += 1
                    continue
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
                            bbox.width if bbox else None,
                            bbox.height if bbox else None,
                            bbox,
                            "absolute",
                            "none",
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
            pages.append(SourcePage(
                page_index,
                page.rect.width * PT_TO_MM,
                page.rect.height * PT_TO_MM,
                tuple(elements),
            ))
    finally:
        document.close()
    return SourceDocument(path, tuple(pages), tuple(dict.fromkeys(warnings)))


def _pdf_paragraph_model(
    line: dict[str, object], page_width_pt: float, body_font_size: float | None
) -> SourceParagraph:
    spans = line.get("spans", [])
    if not isinstance(spans, list):
        spans = []
    runs = tuple(
        SourceTextRun(
            str(span.get("text", "")),
            SourceTextStyle(
                bold="bold" in str(span.get("font", "")).casefold(),
                italic="italic" in str(span.get("font", "")).casefold(),
                font_size_pt=float(span["size"]) if span.get("size") else None,
            ),
        )
        for span in spans
        if span.get("text")
    )
    raw_bbox = line.get("bbox")
    bbox = _bbox(raw_bbox)
    alignment = None
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        x0, _, x1, _ = map(float, raw_bbox)
        line_width = x1 - x0
        center_error = abs((x0 + x1) / 2.0 - page_width_pt / 2.0)
        if line_width < page_width_pt * 0.80 and center_error <= 8.5:  # about 3 mm
            alignment = "center"
    sizes = [run.style.font_size_pt for run in runs if run.style.font_size_pt]
    average_size = sum(sizes) / len(sizes) if sizes else None
    semantic_role = "body"
    if (
        body_font_size
        and average_size
        and average_size >= body_font_size * 1.5
        and len("".join(run.text for run in runs)) <= 120
    ):
        semantic_role = "heading_1"
    return SourceParagraph(
        runs,
        alignment=alignment,
        semantic_role=semantic_role,
        bbox=bbox,
    )


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
    return SourceBBox(x0 * PT_TO_MM, y0 * PT_TO_MM, x1 * PT_TO_MM, y1 * PT_TO_MM)


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
    elements: list[
        SourceTextElement | SourceRasterImageElement | SourceVectorElement | SourceMathElement
    ],
) -> tuple[
    list[SourceTextElement | SourceRasterImageElement | SourceVectorElement | SourceMathElement],
    list[str],
]:
    rasters = [item for item in elements if isinstance(item, SourceRasterImageElement)]
    kept: list[
        SourceTextElement | SourceRasterImageElement | SourceVectorElement | SourceMathElement
    ] = []
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


def _single_pdf_line(drawing: dict[str, object]):
    items = drawing.get("items", [])
    if len(items) == 1 and items[0][0] == "l":
        return items[0][1], items[0][2]
    return None


def _classify_pdf_line(start: object, end: object, blocks: list[dict[str, object]]) -> tuple[str, float]:
    if abs(float(start.y) - float(end.y)) > 0.5:
        return "line", 0.2
    line_y = float(start.y)
    line_x0, line_x1 = sorted((float(start.x), float(end.x)))
    for block in blocks:
        if block.get("type") != 0:
            continue
        x0, _y0, x1, y1 = (float(value) for value in block.get("bbox", (0, 0, 0, 0)))
        overlap = max(0.0, min(x1, line_x1) - max(x0, line_x0))
        ratio = overlap / max(1.0, min(x1 - x0, line_x1 - line_x0))
        if -2 <= line_y - y1 <= 5 and ratio >= 0.7:
            return "underline", 0.95
    return "line", 0.4


def _detect_pdf_arrows(
    drawings: list[dict[str, object]], page_index: int, order: int, claimed: set[int]
) -> tuple[list[SourceArrowElement], set[int]]:
    result: list[SourceArrowElement] = []
    used: set[int] = set()
    for shaft_index, shaft in enumerate(drawings):
        if shaft_index in claimed or (line := _single_pdf_line(shaft)) is None:
            continue
        start, end = line
        shaft_length = math.hypot(end.x - start.x, end.y - start.y) * PT_TO_MM
        if shaft_length < 2:
            continue
        for head_index, head in enumerate(drawings):
            if head_index in claimed or head_index == shaft_index:
                continue
            head_items = head.get("items", [])
            if len(head_items) not in {2, 3} or any(item[0] != "l" for item in head_items):
                continue
            head_points = [point for item in head_items for point in item[1:3]]
            matched_end = next((tip for tip in (start, end) if any(math.hypot(tip.x - point.x, tip.y - point.y) * PT_TO_MM <= 1.2 for point in head_points)), None)
            if matched_end is None:
                continue
            result.append(SourceArrowElement(
                f"page-{page_index + 1:03d}-arrow-{len(result) + 1:03d}",
                order + len(result), page_index,
                (SourcePoint(start.x * PT_TO_MM, start.y * PT_TO_MM), SourcePoint(end.x * PT_TO_MM, end.y * PT_TO_MM)),
                matched_end is start, matched_end is end, "open",
                _bbox(shaft.get("rect")), 0.95,
            ))
            used.update({shaft_index, head_index})
            break
    return result, used


def _detect_pdf_table(
    blocks: list[dict[str, object]], drawings: list[dict[str, object]], page_index: int, order: int
) -> tuple[SourceTableElement | None, set[int], set[int]]:
    horizontal: list[tuple[int, float, float, float]] = []
    vertical: list[tuple[int, float, float, float]] = []
    for index, drawing in enumerate(drawings):
        if (line := _single_pdf_line(drawing)) is None:
            continue
        start, end = line
        if abs(start.y - end.y) <= 0.5:
            horizontal.append((index, float(start.y), min(start.x, end.x), max(start.x, end.x)))
        elif abs(start.x - end.x) <= 0.5:
            vertical.append((index, float(start.x), min(start.y, end.y), max(start.y, end.y)))
    xs = sorted({round(item[1], 2) for item in vertical})
    ys = sorted({round(item[1], 2) for item in horizontal})
    if len(xs) < 3 or len(ys) < 3:
        return None, set(), set()
    left, right, top, bottom = xs[0], xs[-1], ys[0], ys[-1]
    used_drawings = {
        index for index, y, x0, x1 in horizontal if top <= y <= bottom and x0 <= left + 1 and x1 >= right - 1
    } | {
        index for index, x, y0, y1 in vertical if left <= x <= right and y0 <= top + 1 and y1 >= bottom - 1
    }
    if len(used_drawings) < len(xs) + len(ys):
        return None, set(), set()
    texts: dict[tuple[int, int], list[str]] = {}
    used_blocks: set[int] = set()
    for block_index, block in enumerate(blocks):
        if block.get("type") != 0:
            continue
        bx0, by0, bx1, by1 = (float(value) for value in block.get("bbox", (0, 0, 0, 0)))
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if not (left <= cx <= right and top <= cy <= bottom):
            continue
        column = min(len(xs) - 2, max(0, next((i for i in range(len(xs) - 1) if xs[i] <= cx <= xs[i + 1]), 0)))
        row = min(len(ys) - 2, max(0, next((i for i in range(len(ys) - 1) if ys[i] <= cy <= ys[i + 1]), 0)))
        text = " ".join("".join(span.get("text", "") for span in line.get("spans", [])) for line in block.get("lines", []))
        texts.setdefault((row, column), []).append(text)
        used_blocks.add(block_index)
    cells = tuple(
        SourceTableCell(row, column, 1, 1, (SourceParagraph((SourceTextRun(" ".join(texts.get((row, column), []))),)),))
        for row in range(len(ys) - 1) for column in range(len(xs) - 1)
    )
    return SourceTableElement(
        f"page-{page_index + 1:03d}-table-{order + 1:03d}", order, page_index,
        len(ys) - 1, len(xs) - 1, cells,
        tuple((xs[index + 1] - xs[index]) * PT_TO_MM for index in range(len(xs) - 1)),
        SourceBBox(left * PT_TO_MM, top * PT_TO_MM, right * PT_TO_MM, bottom * PT_TO_MM),
        source_kind="pdf-table",
    ), used_blocks, used_drawings
