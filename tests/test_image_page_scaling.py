from pathlib import Path

from plotter_processor.document_models import (
    SourceBBox,
    SourceRasterImageElement,
    SourceVectorElement,
)
from plotter_processor.document_paginator import _image_size, _vector_size
from plotter_processor.graphic_placement import (
    place_raster,
    placement_record,
    rotate_image_point,
    rotated_size,
    scaled_padding,
)
from plotter_processor.layout_models import RectMM
from plotter_processor.models import PlotterStroke, Point


def _raster(width: float, *, rotation: float = 0) -> SourceRasterImageElement:
    return SourceRasterImageElement(
        "image", 0, 0, Path("image.png"), 400, 200, width, width / 2,
        SourceBBox(150, 30, 150 + width, 30 + width / 2),
        "anchored", "square", rotation_deg=rotation,
    )


def test_raster_aspect_small_image_and_oversized_image() -> None:
    small = _image_size(_raster(30), 128, 180, 0.75, 0.60, 0.7)
    large = _image_size(_raster(300), 128, 180, 0.75, 0.60, 0.7)

    assert small == (21, 10.5)
    assert small[0] < 128 * 0.75
    assert large[0] <= 128
    assert large[0] / large[1] == 2


def test_vector_uses_uniform_page_scale() -> None:
    vector = SourceVectorElement(
        "vector", 0, 0,
        (PlotterStroke(0, [Point(0, 0), Point(100, 50)], False),),
    )

    width, height = _vector_size(vector, 128, 180, 0.68)

    assert (width, height) == (68, 34)


def test_rotation_bbox_and_wrap_padding_are_scaled_and_clamped() -> None:
    width, height = rotated_size(40, 20, 90)

    assert abs(width - 20) < 1e-9
    assert abs(height - 40) < 1e-9
    assert scaled_padding(2, 0.68, {"min_wrap_padding_mm": 0.7}) == 1.36
    assert scaled_padding(0.1, 0.1, {"min_wrap_padding_mm": 0.7}) == 0.7


def test_hybrid_right_image_remains_right_and_near_anchor() -> None:
    image = _raster(30)
    content = RectMM(10, 10, 128, 180)
    mapped = RectMM(115, 35, 21, 10.5)
    placed, wrap, warnings = place_raster(
        image, "hybrid", mapped, 21, 10.5, 20, content, [], {}, 2
    )

    assert placed.center[0] > content.center[0]
    assert placed.x == mapped.x
    assert wrap == "square"
    assert not warnings


def test_rotation_and_placement_record_are_stable() -> None:
    target = RectMM(10, 20, 20, 40)

    assert rotate_image_point(Point(0, 0), target, 40, 20, 90) == Point(30, 20)
    assert placement_record(
        "image",
        3,
        0,
        1,
        SourceBBox(1, 2, 41, 22),
        RectMM(11, 12, 20, 10),
        RectMM(12, 14, 20, 10),
        "anchored",
        "square",
        "right",
        40,
        ["image_overlap_avoided", "image_overlap_avoided"],
        "raster-image",
        "activated_at_source_order",
    ) == {
        "id": "image",
        "element_type": "raster-image",
        "source_order": 3,
        "source_page_index": 0,
        "source_bbox_mm": {"x": 1, "y": 2, "width": 40, "height": 20},
        "mapped_bbox_mm": {"x": 11, "y": 12, "width": 20, "height": 10},
        "output_bbox_mm": {"x": 12, "y": 14, "width": 20, "height": 10},
        "target_page_index": 1,
        "anchor": "anchored",
        "wrap_mode": "square",
        "wrap_side": "right",
        "scale": 0.5,
        "center_displacement_mm": 2.236068,
        "overlap_area_mm2": 0.0,
        "page_overflow_area_mm2": 0.0,
        "fallbacks": ["image_overlap_avoided"],
        "placement_reason": "activated_at_source_order",
    }


def test_hybrid_overlap_uses_existing_top_bottom_fallback_policy() -> None:
    image = _raster(30)
    content = RectMM(10, 10, 128, 180)
    mapped = RectMM(20, 30, 21, 10.5)
    previous = [{"output_bbox_mm": {"x": 20, "y": 30, "width": 21, "height": 12}}]

    placed, wrap, warnings = place_raster(
        image,
        "hybrid",
        mapped,
        21,
        10.5,
        20,
        content,
        previous,
        {"max_vertical_shift_mm": 1, "image_padding_mm": 2},
        2,
    )

    assert placed == RectMM(20, 22, 21, 10.5)
    assert wrap == "top_bottom"
    assert warnings == ["image_wrap_fallback_top_bottom"]
