from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True, slots=True)
class CounterAnalysis:
    count: int
    significant_count: int
    preservation_ratio: float
    labels: np.ndarray


def analyze_counters(
    mask: np.ndarray, reconstructed: np.ndarray, *, minimum_area_px: int = 4
) -> CounterAnalysis:
    holes = ndimage.binary_fill_holes(mask) & ~mask
    labels, count = ndimage.label(holes)
    significant: list[int] = []
    preserved = 0
    for label in range(1, count + 1):
        area = labels == label
        if int(area.sum()) < minimum_area_px:
            continue
        significant.append(label)
        # A counter remains represented when reconstruction does not bridge most of its interior.
        filled_ratio = float((reconstructed & area).sum()) / max(1, int(area.sum()))
        if filled_ratio < 0.5:
            preserved += 1
    ratio = preserved / len(significant) if significant else 1.0
    return CounterAnalysis(count, len(significant), round(ratio, 6), labels)
