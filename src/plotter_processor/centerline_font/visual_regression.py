from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial.distance import directed_hausdorff

from plotter_processor.centerline_font.models import CenterlineGlyph


@dataclass(frozen=True, slots=True)
class GeometryComparison:
    stroke_count_delta: int
    point_count_delta: int
    bbox_delta: float
    hausdorff_distance: float


def glyph_snapshot(glyph: CenterlineGlyph, *, sample_count: int = 256) -> dict[str, object]:
    points = np.asarray([(p.x, p.y) for stroke in glyph.strokes for p in stroke.points], dtype=float)
    if points.size == 0:
        sampled: list[list[float]] = []
        bbox = [0.0, 0.0, 0.0, 0.0]
    else:
        indices = np.linspace(0, len(points) - 1, min(sample_count, len(points)), dtype=int)
        sampled = [[round(float(value), 6) for value in point] for point in points[indices]]
        bbox = [
            round(float(points[:, 0].min()), 6),
            round(float(points[:, 1].min()), 6),
            round(float(points[:, 0].max()), 6),
            round(float(points[:, 1].max()), 6),
        ]
    return {
        "char": glyph.char,
        "glyph_name": glyph.glyph_name,
        "stroke_count": len(glyph.strokes),
        "component_count": len({stroke.component_id for stroke in glyph.strokes}),
        "endpoint_count": int(glyph.quality.get("endpoints", 0)),
        "point_count": sum(len(stroke.points) for stroke in glyph.strokes),
        "bbox": bbox,
        "sampled_points": sampled,
        "mask_coverage": glyph.quality.get("mask_coverage"),
        "reconstruction_extra": glyph.quality.get("reconstruction_extra"),
    }


def compare_snapshots(left: dict[str, object], right: dict[str, object]) -> GeometryComparison:
    a = np.asarray(left["sampled_points"], dtype=float)
    b = np.asarray(right["sampled_points"], dtype=float)
    hausdorff = 0.0
    if a.size and b.size:
        hausdorff = max(directed_hausdorff(a, b)[0], directed_hausdorff(b, a)[0])
    left_bbox = np.asarray(left["bbox"], dtype=float)
    right_bbox = np.asarray(right["bbox"], dtype=float)
    bbox_delta = float(np.max(np.abs(left_bbox - right_bbox)))
    return GeometryComparison(
        int(right["stroke_count"]) - int(left["stroke_count"]),
        int(right["point_count"]) - int(left["point_count"]),
        round(bbox_delta, 6),
        round(float(hausdorff), 6) if math.isfinite(hausdorff) else float("inf"),
    )
