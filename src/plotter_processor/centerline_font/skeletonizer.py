from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage.morphology import medial_axis, skeletonize


@dataclass(frozen=True, slots=True)
class SkeletonResult:
    mask: np.ndarray
    distance: np.ndarray
    component_labels: np.ndarray


def build_skeleton(mask: np.ndarray, *, method: str = "medial_axis") -> SkeletonResult:
    source = np.asarray(mask, dtype=bool)
    labels, count = ndimage.label(source, structure=np.ones((3, 3), dtype=np.uint8))
    result = np.zeros_like(source)
    distance = ndimage.distance_transform_edt(source)
    for label in range(1, count + 1):
        component = labels == label
        if method == "medial_axis":
            part = medial_axis(component, rng=0)
        elif method == "skeletonize":
            part = skeletonize(component)
        else:
            raise ValueError(f"Unknown skeleton method: {method}")
        result |= part
    return SkeletonResult(result, distance, labels)


def prune_short_spurs(
    skeleton: np.ndarray,
    distance: np.ndarray,
    *,
    min_branch_width_factor: float,
) -> np.ndarray:
    result = np.asarray(skeleton, dtype=bool).copy()
    if min_branch_width_factor <= 0:
        return result
    for _ in range(32):
        degrees = _degrees(result)
        endpoints = list(zip(*np.nonzero(result & (degrees == 1)), strict=True))
        removed = False
        for endpoint in endpoints:
            branch = [endpoint]
            previous = None
            current = endpoint
            while True:
                neighbors = [p for p in _neighbors(current, result) if p != previous]
                if len(neighbors) != 1:
                    break
                previous, current = current, neighbors[0]
                branch.append(current)
                if _degrees_at(result, current) >= 3:
                    widths = [2 * distance[p] for p in branch]
                    limit = float(np.median(widths)) * min_branch_width_factor
                    if len(branch) - 1 < limit and result.sum() > len(branch):
                        for pixel in branch[:-1]:
                            result[pixel] = False
                        removed = True
                    break
        if not removed:
            break
    return result


def _degrees(mask: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    return ndimage.convolve(mask.astype(np.uint8), kernel, mode="constant")


def _degrees_at(mask: np.ndarray, pixel: tuple[int, int]) -> int:
    return len(_neighbors(pixel, mask))


def _neighbors(pixel: tuple[int, int], mask: np.ndarray) -> list[tuple[int, int]]:
    y, x = pixel
    height, width = mask.shape
    return [
        (ny, nx)
        for ny in range(max(0, y - 1), min(height, y + 2))
        for nx in range(max(0, x - 1), min(width, x + 2))
        if (ny, nx) != pixel and mask[ny, nx]
    ]
