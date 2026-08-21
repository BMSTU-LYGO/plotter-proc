from __future__ import annotations

import math
from itertools import groupby

from plotter_processor.models import PathDocument, PlotterStroke, Point


def optimize_paths(document: PathDocument) -> PathDocument:
    source = [stroke for stroke in document.strokes if isinstance(stroke, PlotterStroke)]
    optimized: list[PlotterStroke] = []
    previous: Point | None = None
    for _, group_iterator in groupby(
        source, key=lambda stroke: stroke.element_id or f"glyph:{stroke.glyph_index}"
    ):
        remaining = [_copy_stroke(stroke) for stroke in group_iterator]
        while remaining:
            selected_index, selected = _nearest_variant(remaining, previous)
            remaining.pop(selected_index)
            optimized.append(selected)
            previous = selected.points[-1]
    for index, stroke in enumerate(optimized):
        stroke.id = index
    return PathDocument(
        page_width_mm=document.page_width_mm,
        page_height_mm=document.page_height_mm,
        strokes=optimized,
        warnings=list(document.warnings),
        metadata=dict(document.metadata),
    )


def _nearest_variant(
    strokes: list[PlotterStroke], previous: Point | None
) -> tuple[int, PlotterStroke]:
    if previous is None:
        return 0, strokes[0]
    best_index = 0
    best_stroke = _orient(strokes[0], previous)
    best_distance = _distance(previous, best_stroke.points[0])
    for index, stroke in enumerate(strokes[1:], start=1):
        candidate = _orient(stroke, previous)
        distance = _distance(previous, candidate.points[0])
        if distance < best_distance:
            best_index, best_stroke, best_distance = index, candidate, distance
    return best_index, best_stroke


def _orient(stroke: PlotterStroke, previous: Point) -> PlotterStroke:
    candidate = _copy_stroke(stroke)
    if candidate.preserve_order:
        return candidate
    if candidate.closed:
        start = min(
            range(len(candidate.points)),
            key=lambda index: _distance(previous, candidate.points[index]),
        )
        candidate.points = candidate.points[start:] + candidate.points[:start]
    elif _distance(previous, candidate.points[-1]) < _distance(previous, candidate.points[0]):
        candidate.points.reverse()
    return candidate


def _copy_stroke(stroke: PlotterStroke) -> PlotterStroke:
    return PlotterStroke(
        id=stroke.id,
        points=list(stroke.points),
        closed=stroke.closed,
        glyph_index=stroke.glyph_index,
        char=stroke.char,
        contour_index=stroke.contour_index,
        source_glyph_indices=stroke.source_glyph_indices,
        source_chars=stroke.source_chars,
        segment_types=stroke.segment_types,
        word_index=stroke.word_index,
        connection_ids=stroke.connection_ids,
        element_id=stroke.element_id,
        element_type=stroke.element_type,
        font_role=stroke.font_role,
        font_sha256=stroke.font_sha256,
        source_path=stroke.source_path,
        source_page_index=stroke.source_page_index,
        semantic_role=stroke.semantic_role,
        layout_group=stroke.layout_group,
        preserve_order=stroke.preserve_order,
        z_order=stroke.z_order,
    )


def _distance(left: Point, right: Point) -> float:
    return math.hypot(right.x - left.x, right.y - left.y)
