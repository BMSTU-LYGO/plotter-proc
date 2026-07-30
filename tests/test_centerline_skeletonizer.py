import numpy as np

from plotter_processor.centerline_font.skeletonizer import build_skeleton


def test_ring_produces_deterministic_centerline_loop() -> None:
    y, x = np.ogrid[:41, :41]
    radius = np.sqrt((x - 20) ** 2 + (y - 20) ** 2)
    mask = (radius >= 10) & (radius <= 15)
    first = build_skeleton(mask, method="medial_axis").mask
    second = build_skeleton(mask, method="medial_axis").mask
    assert np.array_equal(first, second)
    assert first.any()
    assert not first[20, 20]
