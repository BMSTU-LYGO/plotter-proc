from __future__ import annotations

import numpy as np
from scipy import ndimage
from skimage.morphology import closing, disk

from plotter_processor.centerline_font.models import RasterGlyph


def build_ink_mask(raster: RasterGlyph, *, threshold: int, closing_radius_px: int) -> np.ndarray:
    if not 1 <= threshold <= 254:
        raise ValueError("threshold must be between 1 and 254")
    if closing_radius_px < 0:
        raise ValueError("closing_radius_px must be non-negative")
    mask = np.asarray(raster.grayscale < threshold, dtype=bool)
    if closing_radius_px:
        mask = closing(mask, disk(closing_radius_px))
    if not mask.any():
        raise ValueError(f'Glyph "{raster.char}" produced an empty ink mask')
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        raise ValueError(f'Glyph "{raster.char}" touches raster canvas edge')
    _, components = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    if components < 1:
        raise ValueError("Ink mask contains no connected components")
    return mask
