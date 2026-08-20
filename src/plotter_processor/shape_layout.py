from __future__ import annotations

import math

from plotter_processor.document_models import SourceArrowElement, SourceLineElement
from plotter_processor.models import PlotterStroke, Point


def line_strokes(element: SourceLineElement, *, x: float = 0, y: float = 0) -> list[PlotterStroke]:
    return [PlotterStroke(
        0,
        [Point(x + element.start.x_mm, y + element.start.y_mm), Point(x + element.end.x_mm, y + element.end.y_mm)],
        False,
        element_id=element.id,
        element_type="text-decoration" if element.semantic_role == "underline" else "line",
        semantic_role=element.semantic_role,
        segment_types=(element.semantic_role,),
        preserve_order=element.semantic_role == "underline",
    )]


def arrow_strokes(element: SourceArrowElement, *, x: float = 0, y: float = 0) -> list[PlotterStroke]:
    points = [Point(x + point.x_mm, y + point.y_mm) for point in element.points]
    if len(points) < 2:
        return []
    result = [PlotterStroke(
        0, points, False, element_id=element.id, element_type="arrow",
        semantic_role="arrow-shaft", segment_types=("arrow-shaft",), preserve_order=True,
    )]
    if element.head_at_start:
        result.extend(_head(points[0], points[1], element.id, len(result), "start"))
    if element.head_at_end:
        result.extend(_head(points[-1], points[-2], element.id, len(result), "end"))
    return result


def _head(tip: Point, inward: Point, element_id: str, index: int, side: str) -> list[PlotterStroke]:
    angle = math.atan2(inward.y - tip.y, inward.x - tip.x)
    length = min(3.0, max(1.2, math.hypot(inward.x - tip.x, inward.y - tip.y) * 0.18))
    left = Point(tip.x + length * math.cos(angle + 0.55), tip.y + length * math.sin(angle + 0.55))
    right = Point(tip.x + length * math.cos(angle - 0.55), tip.y + length * math.sin(angle - 0.55))
    return [PlotterStroke(
        index, [left, tip, right], False, element_id=element_id, element_type="arrow",
        semantic_role=f"arrow-head-{side}", segment_types=("arrow-head",), preserve_order=True,
    )]
