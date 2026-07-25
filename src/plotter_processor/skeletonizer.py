from pathlib import Path

import numpy as np
from PIL import Image
from skimage import measure, morphology

DEFAULT_MAX_SKELETON_PIXELS = 2_000_000
GIANT_COMPONENT_PAGE_FRACTION = 0.80


def skeletonize_image(
    image: np.ndarray,
    *,
    threshold: int,
    remove_small_objects_px: int,
    content_bounds: tuple[int, int, int, int] | None = None,
    max_skeleton_pixels: int = DEFAULT_MAX_SKELETON_PIXELS,
) -> np.ndarray:
    grayscale = _as_grayscale(image)
    if not 0 <= threshold <= 255:
        raise ValueError("threshold must be between 0 and 255")
    if remove_small_objects_px < 1:
        raise ValueError("remove_small_objects_px must be at least 1")
    if max_skeleton_pixels < 1:
        raise ValueError("max_skeleton_pixels must be positive")

    ink = grayscale < threshold
    try:
        ink = morphology.remove_small_objects(ink, max_size=remove_small_objects_px - 1)
    except TypeError:
        # scikit-image 0.24 and 0.25 use min_size instead of max_size.
        ink = morphology.remove_small_objects(ink, min_size=remove_small_objects_px)
    if not np.any(ink):
        raise ValueError("Skeleton is empty. The rendered page contains no usable ink.")

    _validate_giant_component(ink)
    skeleton = morphology.skeletonize(ink)

    pixel_count = int(np.count_nonzero(skeleton))
    if pixel_count == 0:
        raise ValueError("Skeleton is empty after skeletonization.")
    if pixel_count > max_skeleton_pixels:
        raise ValueError(
            f"Skeleton contains {pixel_count} pixels, exceeding the safe limit "
            f"of {max_skeleton_pixels}."
        )
    if content_bounds is not None:
        _validate_content_bounds(skeleton, content_bounds)

    return np.asarray(skeleton, dtype=bool)


def save_skeleton(skeleton: np.ndarray, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic = np.where(skeleton, 0, 255).astype(np.uint8)
    Image.fromarray(diagnostic).save(path)


def _as_grayscale(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[2] in (3, 4):
        rgb = array[..., :3].astype(np.float32)
        return np.round(rgb @ np.array([0.299, 0.587, 0.114])).astype(np.uint8)
    raise ValueError("Input image must be a grayscale, RGB, or RGBA array")


def _validate_giant_component(ink: np.ndarray) -> None:
    labels = measure.label(ink, connectivity=2)
    component_sizes = np.bincount(labels.ravel())[1:]
    if component_sizes.size == 0:
        return
    largest_fraction = float(component_sizes.max()) / ink.size
    if largest_fraction >= GIANT_COMPONENT_PAGE_FRACTION:
        raise ValueError("A giant ink component covers almost the entire page.")


def _validate_content_bounds(
    skeleton: np.ndarray, bounds: tuple[int, int, int, int]
) -> None:
    left, top, right, bottom = bounds
    height, width = skeleton.shape
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Content bounds are outside the image")

    outside = skeleton.copy()
    outside[top:bottom, left:right] = False
    if np.any(outside):
        raise ValueError("Ink was found outside the configured page margins.")
