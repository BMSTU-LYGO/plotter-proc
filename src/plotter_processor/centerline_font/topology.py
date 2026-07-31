from __future__ import annotations

import numpy as np

Pixel = tuple[int, int]
OFFSETS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))


def topology_neighbors(
    pixel: Pixel,
    skeleton: np.ndarray,
    *,
    suppress_corner_diagonals: bool = True,
) -> tuple[Pixel, ...]:
    y, x = pixel
    result: list[Pixel] = []
    for dy, dx in OFFSETS:
        ny, nx = y + dy, x + dx
        if not (0 <= ny < skeleton.shape[0] and 0 <= nx < skeleton.shape[1] and skeleton[ny, nx]):
            continue
        if suppress_corner_diagonals and dy and dx and (skeleton[y, nx] or skeleton[ny, x]):
            continue
        result.append((ny, nx))
    return tuple(result)


def crossing_number(
    pixel: Pixel, skeleton: np.ndarray, *, suppress_corner_diagonals: bool = True
) -> int:
    neighbors = set(
        topology_neighbors(
            pixel, skeleton, suppress_corner_diagonals=suppress_corner_diagonals
        )
    )
    y, x = pixel
    values = [int((y + dy, x + dx) in neighbors) for dy, dx in OFFSETS]
    return sum(abs(values[index] - values[(index + 1) % 8]) for index in range(8)) // 2


def classify_skeleton_pixel(
    pixel: Pixel, skeleton: np.ndarray, *, suppress_corner_diagonals: bool = True
) -> str:
    cn = crossing_number(
        pixel, skeleton, suppress_corner_diagonals=suppress_corner_diagonals
    )
    if not topology_neighbors(
        pixel, skeleton, suppress_corner_diagonals=suppress_corner_diagonals
    ):
        return "isolated"
    if cn == 1:
        return "endpoint"
    if cn == 2:
        return "regular"
    if cn >= 3:
        return "junction"
    return "isolated"
