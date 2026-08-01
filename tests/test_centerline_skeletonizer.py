import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.skeletonizer import build_skeleton, prune_short_spurs


def test_ring_produces_deterministic_centerline_loop() -> None:
    y, x = np.ogrid[:41, :41]
    radius = np.sqrt((x - 20) ** 2 + (y - 20) ** 2)
    mask = (radius >= 10) & (radius <= 15)
    first = build_skeleton(mask, method="medial_axis").mask
    second = build_skeleton(mask, method="medial_axis").mask
    assert np.array_equal(first, second)
    assert first.any()
    assert not first[20, 20]


def test_width_aware_pruning_keeps_long_thin_tail() -> None:
    skeleton = np.zeros((25, 25), dtype=bool)
    skeleton[4:21, 12] = True
    skeleton[12, 13:22] = True
    distance = np.ones_like(skeleton, dtype=float)
    result = prune_short_spurs(
        skeleton, distance, min_branch_width_factor=1.5, ink_mask=skeleton
    )
    assert result[12, 21]


def test_pruning_is_cancelled_when_coverage_loss_is_too_large() -> None:
    skeleton = np.zeros((20, 20), dtype=bool)
    skeleton[3:12, 7] = True
    skeleton[7, 8:13] = True
    distance = np.ones_like(skeleton, dtype=float) * 3
    result = prune_short_spurs(
        skeleton,
        distance,
        min_branch_width_factor=2.0,
        ink_mask=ndimage.binary_dilation(skeleton, iterations=2),
        max_coverage_loss=0.0,
        preserve_connector_terminals=False,
    )
    assert result[7, 12]
