from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from plotter_processor.skeletonizer import save_skeleton, skeletonize_image


def test_skeletonizes_thick_line_to_thin_path() -> None:
    image = np.full((30, 30), 255, dtype=np.uint8)
    image[13:17, 5:25] = 0

    skeleton = skeletonize_image(
        image,
        threshold=180,
        remove_small_objects_px=4,
        content_bounds=(2, 2, 28, 28),
    )

    assert skeleton.dtype == np.bool_
    assert 10 <= np.count_nonzero(skeleton) <= 25
    assert np.count_nonzero(skeleton) < np.count_nonzero(image < 180)


def test_removes_small_noise_objects() -> None:
    image = np.full((30, 30), 255, dtype=np.uint8)
    image[10:14, 5:25] = 0
    image[2, 2] = 0

    skeleton = skeletonize_image(
        image,
        threshold=180,
        remove_small_objects_px=4,
        content_bounds=(1, 1, 29, 29),
    )

    assert not skeleton[2, 2]


def test_rejects_empty_skeleton() -> None:
    image = np.full((20, 20), 255, dtype=np.uint8)

    with pytest.raises(ValueError, match="contains no usable ink"):
        skeletonize_image(image, threshold=180, remove_small_objects_px=4)


def test_rejects_ink_outside_margins() -> None:
    image = np.full((30, 30), 255, dtype=np.uint8)
    image[1:5, 1:5] = 0

    with pytest.raises(ValueError, match="outside the configured page margins"):
        skeletonize_image(
            image,
            threshold=180,
            remove_small_objects_px=2,
            content_bounds=(5, 5, 25, 25),
        )


def test_rejects_giant_page_component() -> None:
    image = np.zeros((30, 30), dtype=np.uint8)

    with pytest.raises(ValueError, match="giant ink component"):
        skeletonize_image(image, threshold=180, remove_small_objects_px=2)


def test_enforces_skeleton_pixel_limit() -> None:
    image = np.full((30, 30), 255, dtype=np.uint8)
    image[5:25, 5:25] = 0

    with pytest.raises(ValueError, match="safe limit"):
        skeletonize_image(
            image,
            threshold=180,
            remove_small_objects_px=2,
            max_skeleton_pixels=2,
        )


def test_saves_black_skeleton_on_white_background(tmp_path: Path) -> None:
    skeleton = np.zeros((10, 10), dtype=bool)
    skeleton[5, 2:8] = True
    output = tmp_path / "skeleton.png"

    save_skeleton(skeleton, output)

    saved = np.asarray(Image.open(output))
    assert saved[5, 4] == 0
    assert saved[0, 0] == 255
