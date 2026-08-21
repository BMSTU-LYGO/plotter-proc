from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

from plotter_processor.font_loader import load_font
from plotter_processor.models import PageSpec, PathDocument, PlotterStroke


def validate_vector_font(font_path: str | Path, text: str = "") -> None:
    with load_font(font_path) as font:
        if text:
            font.validate_text(text)


def validate_page_spec(page: PageSpec, margins: Mapping[str, object]) -> None:
    if page.width_mm <= 0 or page.height_mm <= 0:
        raise ValueError("Page dimensions must be positive")
    values: dict[str, float] = {}
    for key in ("left", "right", "top", "bottom"):
        value = margins.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Missing or invalid page margin: {key}")
        values[key] = float(value)
    if values["left"] + values["right"] >= page.width_mm:
        raise ValueError("Horizontal margins leave no usable page area")
    if values["top"] + values["bottom"] >= page.height_mm:
        raise ValueError("Vertical margins leave no usable page area")


def validate_page_workspace(
    page: PageSpec,
    machine_config: Mapping[str, object],
) -> None:
    origin = _mapping(machine_config, "page_origin_mm")
    workspace = _mapping(machine_config, "workspace_mm")
    origin_x = _number(origin, "x")
    origin_y = _number(origin, "y")
    minimum_x = _number(workspace, "min_x")
    maximum_x = _number(workspace, "max_x")
    minimum_y = _number(workspace, "min_y")
    maximum_y = _number(workspace, "max_y")
    if minimum_x >= maximum_x or minimum_y >= maximum_y:
        raise ValueError("workspace_mm minimums must be smaller than maximums")
    page_bounds = (
        origin_x,
        origin_x + page.width_mm,
        origin_y,
        origin_y + page.height_mm,
    )
    if (
        page_bounds[0] < minimum_x
        or page_bounds[1] > maximum_x
        or page_bounds[2] < minimum_y
        or page_bounds[3] > maximum_y
    ):
        workspace_width = maximum_x - minimum_x
        workspace_height = maximum_y - minimum_y
        raise ValueError(
            f"{page.name} portrait ({page.width_mm:g}×{page.height_mm:g} mm) does not fit "
            f"configured XY workspace {workspace_width:g}×{workspace_height:g} mm at page "
            f"origin ({origin_x:g},{origin_y:g}) mm. Use a compatible machine config, "
            "supported orientation, or smaller page size."
        )


def validate_path_document(document: PathDocument, *, max_points_per_contour: int) -> None:
    if max_points_per_contour < 2:
        raise ValueError("max_points_per_contour must be at least 2")
    if not document.strokes:
        raise ValueError("Font processing produced no drawable paths")
    pipeline = document.metadata.get("pipeline")
    if pipeline not in {None, "ttf-vector", "ttf-centerline", "document-mixed"}:
        raise ValueError(f"Unsupported path pipeline metadata: {pipeline}")
    for stroke in document.strokes:
        if not isinstance(stroke, PlotterStroke):
            raise TypeError("Vector pipeline received a legacy stroke")
        if len(stroke.points) > max_points_per_contour:
            raise ValueError(f"Stroke {stroke.id} exceeds max_points_per_contour")
        unique_points = len({(point.x, point.y) for point in stroke.points})
        minimum = 3 if stroke.closed else 2
        if unique_points < minimum:
            raise ValueError(
                f"Stroke {stroke.id} has fewer than {minimum} unique points"
            )
        length = 0.0
        for index, point in enumerate(stroke.points):
            if not math.isfinite(point.x) or not math.isfinite(point.y):
                raise ValueError(f"Stroke {stroke.id} contains non-finite coordinates")
            if not (
                0 <= point.x <= document.page_width_mm and 0 <= point.y <= document.page_height_mm
            ):
                raise ValueError(f"Stroke {stroke.id} lies outside the page bounds")
            if index:
                previous = stroke.points[index - 1]
                length += math.hypot(point.x - previous.x, point.y - previous.y)
        if stroke.closed:
            length += math.hypot(
                stroke.points[0].x - stroke.points[-1].x,
                stroke.points[0].y - stroke.points[-1].y,
            )
        if length <= 0:
            raise ValueError(f"Stroke {stroke.id} has zero length")


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid mapping field: {key}")
    return value


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number
