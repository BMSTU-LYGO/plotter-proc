from pathlib import Path

from plotter_processor.document_models import (
    SourceBBox,
    SourceRasterImageElement,
    SourceVectorElement,
)
from plotter_processor.document_paginator import (
    _image_size,
    _place_raster,
    _rotated_size,
    _scaled_padding,
    _vector_size,
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
    width, height = _rotated_size(40, 20, 90)

    assert abs(width - 20) < 1e-9
    assert abs(height - 40) < 1e-9
    assert _scaled_padding(2, 0.68, {"min_wrap_padding_mm": 0.7}) == 1.36
    assert _scaled_padding(0.1, 0.1, {"min_wrap_padding_mm": 0.7}) == 0.7


def test_hybrid_right_image_remains_right_and_near_anchor() -> None:
    image = _raster(30)
    content = RectMM(10, 10, 128, 180)
    mapped = RectMM(115, 35, 21, 10.5)
    placed, wrap, warnings = _place_raster(
        image, "hybrid", mapped, 21, 10.5, 20, content, [], {}, 2
    )

    assert placed.center[0] > content.center[0]
    assert placed.x == mapped.x
    assert wrap == "square"
    assert not warnings

