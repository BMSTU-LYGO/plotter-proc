import numpy as np
import pytest

from plotter_processor.raster_centerline import RasterCenterlineConfig, raster_to_centerline


def test_mask_to_centerline_is_deterministic_and_preserves_bar() -> None:
    mask = np.zeros((40, 80), dtype=bool)
    mask[8:13, 8:72] = True
    mask[25:32, 35:43] = True

    first = raster_to_centerline(mask, 0.05)
    second = raster_to_centerline(mask, 0.05)

    assert first.strokes == second.strokes
    assert first.components == 2
    assert any(
        max(point.x for point in stroke.points) - min(point.x for point in stroke.points) > 2.5
        for stroke in first.strokes
    )


def test_complexity_limit_is_bounded() -> None:
    mask = np.ones((20, 20), dtype=bool)
    config = RasterCenterlineConfig(max_render_pixels=100)

    with pytest.raises(ValueError, match="pixels"):
        raster_to_centerline(mask, 0.1, config)
