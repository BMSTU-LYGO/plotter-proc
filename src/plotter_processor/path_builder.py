from __future__ import annotations

import json
import math
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path

from fontTools.pens.transformPen import TransformPen

from plotter_processor.curve_flattener import CurveFlatteningPen
from plotter_processor.font_loader import LoadedFont
from plotter_processor.models import PageSpec, PathDocument, PlotterStroke, Point, PositionedGlyph


def build_paths(
    font: LoadedFont,
    glyphs: list[PositionedGlyph],
    page: PageSpec,
    vector_options: Mapping[str, object],
) -> PathDocument:
    strokes: list[PlotterStroke] = []
    warnings: list[str] = []
    for positioned in glyphs:
        pen = CurveFlatteningPen(
            font.glyph_set,
            tolerance_mm=_number(vector_options, "flatten_tolerance_mm"),
            min_segment_length_mm=_number(vector_options, "min_segment_length_mm"),
            max_points_per_contour=_integer(vector_options, "max_points_per_contour"),
            max_recursion_depth=_integer(vector_options, "max_recursion_depth"),
        )
        transform = (
            positioned.scale_mm_per_font_unit,
            0,
            0,
            -positioned.scale_mm_per_font_unit,
            positioned.x_mm,
            positioned.baseline_y_mm,
        )
        font.glyph_set[positioned.glyph_name].draw(TransformPen(pen, transform))
        warnings.extend(pen.warnings)
        for contour_index, contour in enumerate(pen.contours):
            unique = {(point.x, point.y) for point in contour.points}
            if len(unique) < 2 or _stroke_length(contour.points, contour.closed) <= 0:
                warnings.append(
                    f"Skipped empty contour {contour_index} for glyph {positioned.glyph_index}"
                )
                continue
            strokes.append(
                PlotterStroke(
                    id=len(strokes),
                    points=contour.points,
                    closed=contour.closed,
                    glyph_index=positioned.glyph_index,
                    char=positioned.char,
                    contour_index=contour_index,
                )
            )
    return PathDocument(
        page_width_mm=page.width_mm,
        page_height_mm=page.height_mm,
        strokes=strokes,
        warnings=list(dict.fromkeys(warnings)),
        metadata={"coordinate_system": "page-mm-top-left", "pipeline": "ttf-vector"},
    )


def save_path_document(document: PathDocument, output_path: str | Path) -> None:
    payload = {
        "format": "plotter-paths",
        "version": 2,
        "page": {
            "width_mm": document.page_width_mm,
            "height_mm": document.page_height_mm,
        },
        "metadata": document.metadata,
        "strokes": [
            {
                "id": stroke.id,
                "glyph_index": stroke.glyph_index,
                "char": stroke.char,
                "contour_index": stroke.contour_index,
                "closed": stroke.closed,
                "source_glyph_indices": list(stroke.source_glyph_indices),
                "source_chars": stroke.source_chars,
                "segment_types": list(stroke.segment_types),
                "word_index": stroke.word_index,
                "connection_ids": list(stroke.connection_ids),
                "element_id": stroke.element_id,
                "element_type": stroke.element_type,
                "font_role": stroke.font_role,
                "font_sha256": stroke.font_sha256,
                "source_path": _stable_source_path(stroke.source_path),
                "source_page_index": stroke.source_page_index,
                "semantic_role": stroke.semantic_role,
                "layout_group": stroke.layout_group,
                "preserve_order": stroke.preserve_order,
                "z_order": stroke.z_order,
                "points": [[point.x, point.y] for point in stroke.points],
            }
            for stroke in document.strokes
            if isinstance(stroke, PlotterStroke)
        ],
        "warnings": document.warnings,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_path_document(input_path: str | Path) -> PathDocument:
    path = Path(input_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != "plotter-paths" or payload.get("version") != 2:
            raise ValueError("Unsupported paths JSON format or version")
        page = payload["page"]
        strokes = [
            PlotterStroke(
                id=int(item["id"]),
                glyph_index=item.get("glyph_index"),
                char=item.get("char"),
                contour_index=item.get("contour_index"),
                closed=bool(item["closed"]),
                points=[Point(float(point[0]), float(point[1])) for point in item["points"]],
                source_glyph_indices=tuple(item.get("source_glyph_indices", ())),
                source_chars=str(item.get("source_chars", "")),
                segment_types=tuple(item.get("segment_types", ())),
                word_index=item.get("word_index"),
                connection_ids=tuple(item.get("connection_ids", ())),
                element_id=item.get("element_id"),
                element_type=item.get("element_type"),
                font_role=item.get("font_role"),
                font_sha256=item.get("font_sha256"),
                source_path=item.get("source_path"),
                source_page_index=item.get("source_page_index"),
                semantic_role=item.get("semantic_role"),
                layout_group=item.get("layout_group"),
                preserve_order=bool(item.get("preserve_order", False)),
                z_order=int(item.get("z_order", 0)),
            )
            for item in payload["strokes"]
        ]
        return PathDocument(
            page_width_mm=float(page["width_mm"]),
            page_height_mm=float(page["height_mm"]),
            strokes=strokes,
            warnings=list(payload.get("warnings", [])),
            metadata=dict(payload.get("metadata", {})),
        )
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid paths JSON: {path}") from error


def path_statistics(document: PathDocument) -> dict[str, object]:
    strokes = [stroke for stroke in document.strokes if isinstance(stroke, PlotterStroke)]
    draw = sum(_stroke_length(stroke.points, stroke.closed) for stroke in strokes)
    travel = sum(
        math.dist((left.points[-1].x, left.points[-1].y), (right.points[0].x, right.points[0].y))
        for left, right in pairwise(strokes)
    )
    points = [point for stroke in strokes for point in stroke.points]
    bbox = None
    if points:
        bbox = {
            "min_x": min(point.x for point in points),
            "min_y": min(point.y for point in points),
            "max_x": max(point.x for point in points),
            "max_y": max(point.y for point in points),
        }
    return {
        "contours": len(strokes),
        "strokes": len(strokes),
        "points": len(points),
        "closed_contours": sum(stroke.closed for stroke in strokes),
        "open_contours": sum(not stroke.closed for stroke in strokes),
        "draw_distance_mm": round(draw, 3),
        "travel_distance_mm": round(travel, 3),
        "bounding_box_mm": bbox,
    }


def _stroke_length(points: list[Point], closed: bool) -> float:
    pairs = list(pairwise(points))
    if closed and len(points) > 1:
        pairs.append((points[-1], points[0]))
    return sum(math.hypot(end.x - start.x, end.y - start.y) for start, end in pairs)


def _stable_source_path(source_path: str | None) -> str | None:
    """Keep extracted-asset provenance without serializing a job-local directory."""
    if source_path is None:
        return None
    path = Path(source_path)
    if path.parent.name == "extracted-assets":
        return f"asset://{path.name}"
    return source_path


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Missing or invalid number field: vector.{key}")
    return float(value)


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Missing or invalid integer field: vector.{key}")
    return value
