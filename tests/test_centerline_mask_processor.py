import numpy as np

from plotter_processor.centerline_font.mask_processor import build_ink_mask
from plotter_processor.centerline_font.models import RasterGlyph


def test_mask_preserves_small_disconnected_marks() -> None:
    gray = np.full((20, 20), 255, dtype=np.uint8)
    gray[8:15, 8:12] = 0
    gray[4:6, 9:11] = 0
    raster = RasterGlyph("!", 33, "exclam", 20, 20, 2, 16, 1, 10, gray)
    mask = build_ink_mask(raster, threshold=160, closing_radius_px=0)
    assert mask[4:6, 9:11].all()
    assert mask[8:15, 8:12].all()
