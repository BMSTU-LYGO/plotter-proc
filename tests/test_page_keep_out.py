import pytest

from plotter_processor.models import PageSpec, PathDocument, PlotterStroke, Point
from plotter_processor.page_keep_out import (
    effective_content_margins,
    resolve_keep_out_zones,
    validate_path_keep_outs,
)


def test_configured_holes_include_clearance_in_safe_radius() -> None:
    zones = resolve_keep_out_zones(
        ({"x_mm": 6, "y_mm": 80, "radius_mm": 3},),
        1.5,
        PageSpec("A5", 148, 210),
    )

    assert zones[0].safe_radius_mm == 4.5


def test_any_number_of_holes_is_supported() -> None:
    holes = tuple(
        {"x_mm": 6, "y_mm": 20 + index * 30, "radius_mm": 3}
        for index in range(6)
    )

    assert len(resolve_keep_out_zones(holes, 1, PageSpec("A5", 148, 210))) == 6


def test_left_edge_holes_expand_effective_content_bounds() -> None:
    page = PageSpec("A5", 148, 210)
    zones = resolve_keep_out_zones(
        ({"x_mm": 8, "y_mm": 80, "radius_mm": 4},), 2, page
    )

    margins = effective_content_margins(
        {"left": 10, "right": 10, "top": 10, "bottom": 10}, page, zones
    )

    assert margins["left"] == 14
    assert margins["right"] == 10


def test_draw_segment_intersecting_safe_radius_is_rejected() -> None:
    document = PathDocument(
        148,
        210,
        [PlotterStroke(7, [Point(5, 80), Point(20, 80)], False, element_id="text-1")],
        [],
    )
    zones = [{"x_mm": 8, "y_mm": 80, "radius_mm": 3, "clearance_mm": 1}]

    with pytest.raises(ValueError, match="Page 2, element 'text-1'"):
        validate_path_keep_outs(document, zones, page_number=2)


def test_draw_segment_outside_safe_radius_is_allowed() -> None:
    document = PathDocument(
        148,
        210,
        [PlotterStroke(7, [Point(20, 70), Point(20, 90)], False)],
        [],
    )
    zones = [{"x_mm": 8, "y_mm": 80, "radius_mm": 3, "clearance_mm": 1}]

    validate_path_keep_outs(document, zones)
