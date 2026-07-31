from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.models import CenterlineStroke, RasterGlyph


def score_quality(
    mask: np.ndarray,
    skeleton: np.ndarray,
    strokes: list[CenterlineStroke],
    raster: RasterGlyph,
    *,
    min_coverage: float,
    max_extra: float,
    max_endpoint_factor: float,
) -> tuple[dict[str, object], list[str]]:
    del raster
    radius = max(1, round(float(np.median(ndimage.distance_transform_edt(mask)[skeleton]))))
    reconstructed = ndimage.binary_dilation(skeleton, iterations=radius)
    overlap = int((reconstructed & mask).sum())
    coverage = overlap / max(1, int(mask.sum()))
    extra = int((reconstructed & ~mask).sum()) / max(1, int(reconstructed.sum()))
    connectivity = np.ones((3, 3), dtype=np.uint8)
    _, mask_components = ndimage.label(mask, structure=connectivity)
    _, skeleton_components = ndimage.label(skeleton, structure=connectivity)
    endpoints = sum(not stroke.closed for stroke in strokes) * 2
    warnings: list[str] = []
    if coverage < min_coverage:
        warnings.append("Centerline mask coverage below threshold")
    if extra > max_extra:
        warnings.append("Centerline reconstruction extra area above threshold")
    if skeleton_components < mask_components:
        warnings.append("Connected component was lost")
    if endpoints > max_endpoint_factor * max(1, len(strokes)):
        warnings.append("Centerline has an anomalous endpoint count")
    radii = ndimage.distance_transform_edt(mask)[skeleton]
    mean_radius = float(np.mean(radii)) if radii.size else 0.0
    balance = float(np.std(radii) / mean_radius) if mean_radius else 0.0
    inside_ratio = float((skeleton & mask).sum()) / max(1, int(skeleton.sum()))
    metrics: dict[str, float | int | bool | str] = {
        "mask_coverage": round(coverage, 6),
        "centerline_inside_mask_ratio": round(inside_ratio, 6),
        "distance_to_boundary_balance_cv": round(balance, 6),
        "reconstruction_extra": round(extra, 6),
        "mask_components": int(mask_components),
        "centerline_components": int(skeleton_components),
        "endpoints": endpoints,
        "needs_review": bool(warnings),
        "quality_status": "needs_review" if warnings else "auto_passed",
    }
    return metrics, warnings


def validate_strokes(strokes: list[CenterlineStroke]) -> None:
    for stroke in strokes:
        minimum = 3 if stroke.closed else 2
        if len(set(stroke.points)) < minimum:
            raise ValueError(f"Centerline stroke {stroke.id} has too few unique points")
        if any(not math.isfinite(p.x) or not math.isfinite(p.y) for p in stroke.points):
            raise ValueError(f"Centerline stroke {stroke.id} has non-finite coordinates")
