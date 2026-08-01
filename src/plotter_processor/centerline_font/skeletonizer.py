from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

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
    ink_mask: np.ndarray | None = None,
    max_coverage_loss: float = 0.01,
    preserve_connector_terminals: bool = True,
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
                    local_width = float(np.median(widths))
                    length = _branch_length(branch)
                    ratio = length / max(local_width, 1e-9)
                    # Thin terminals are likely cursive entry/exit tails and are kept in safe mode.
                    terminal_width = float(widths[0]) if widths else 0.0
                    connector_like = terminal_width < local_width * 0.65
                    if (
                        ratio < min_branch_width_factor
                        and result.sum() > len(branch)
                        and not (preserve_connector_terminals and connector_like)
                    ):
                        candidate = result.copy()
                        for pixel in branch[:-1]:
                            candidate[pixel] = False
                        if _coverage_loss(result, candidate, distance, ink_mask) <= max_coverage_loss:
                            result = candidate
                            removed = True
                    break
        if not removed:
            break
    return result


def _branch_length(branch: list[tuple[int, int]]) -> float:
    return sum(
        float(np.hypot(right[0] - left[0], right[1] - left[1]))
        for left, right in pairwise(branch)
    )


def _coverage_loss(
    before: np.ndarray,
    after: np.ndarray,
    distance: np.ndarray,
    ink_mask: np.ndarray | None,
) -> float:
    if ink_mask is None:
        return 0.0
    old = _reconstruct_with_local_radius(before, distance) & ink_mask
    new = _reconstruct_with_local_radius(after, distance) & ink_mask
    return max(0.0, float(old.sum() - new.sum()) / max(1, int(ink_mask.sum())))


def _reconstruct_with_local_radius(skeleton: np.ndarray, radius_map: np.ndarray) -> np.ndarray:
    if not skeleton.any():
        return np.zeros_like(skeleton)
    nearest_distance, indices = ndimage.distance_transform_edt(
        ~skeleton, return_distances=True, return_indices=True
    )
    nearest_radius = radius_map[tuple(indices)]
    return nearest_distance <= nearest_radius


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
