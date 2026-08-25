import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.skeletonizer import (
    _coverage_loss,
    _coverage_loss_from_reconstruction,
    build_skeleton,
    preprocess_skeleton,
    prune_short_spurs,
    reconstruct_with_local_radius,
)


def test_ring_produces_deterministic_centerline_loop() -> None:
    y, x = np.ogrid[:41, :41]
    radius = np.sqrt((x - 20) ** 2 + (y - 20) ** 2)
    mask = (radius >= 10) & (radius <= 15)
    first = build_skeleton(mask, method="medial_axis").mask
    second = build_skeleton(mask, method="medial_axis").mask
    assert np.array_equal(first, second)
    assert first.any()
    assert not first[20, 20]


def test_shared_preprocessing_preserves_each_candidate_byte_for_byte() -> None:
    y, x = np.ogrid[:51, :47]
    mask = ((x - 18) ** 2 + (y - 25) ** 2 <= 13**2) | (
        (x >= 18) & (x <= 39) & (y >= 22) & (y <= 28)
    )
    prepared = preprocess_skeleton(mask)
    boundary = mask & ~ndimage.binary_erosion(mask)
    assert np.array_equal(
        prepared.boundary_distance,
        ndimage.distance_transform_edt(~boundary),
    )

    for index, method in enumerate(("skeletonize", "medial_axis"), start=1):
        reference = build_skeleton(mask, method=method, candidate_index=index)
        shared = build_skeleton(
            mask, method=method, candidate_index=index, prepared=prepared
        )
        assert np.array_equal(shared.mask, reference.mask)
        assert np.array_equal(shared.distance, reference.distance)
        assert np.array_equal(shared.component_labels, reference.component_labels)


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


def test_cached_coverage_loss_is_exactly_the_full_reconstruction_formula() -> None:
    rng = np.random.default_rng(1206)
    for _ in range(20):
        before = rng.random((32, 29)) > 0.91
        after = before.copy()
        after[rng.random(before.shape) > 0.97] = False
        ink = ndimage.binary_dilation(before, iterations=2)
        distance = ndimage.distance_transform_edt(ink)
        old = reconstruct_with_local_radius(before, distance) & ink
        new = reconstruct_with_local_radius(after, distance) & ink

        assert _coverage_loss_from_reconstruction(old, new, ink) == _coverage_loss(
            before, after, distance, ink
        )
