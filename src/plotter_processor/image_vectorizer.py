from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from skimage.feature import canny
from skimage.measure import approximate_polygon, find_contours
from skimage.morphology import skeletonize

from plotter_processor.image_preprocessor import PreprocessedImage
from plotter_processor.models import PlotterStroke, Point


@dataclass(frozen=True, slots=True)
class VectorizedImage:
    strokes: tuple[PlotterStroke, ...]
    mode: str
    point_count: int
    warnings: tuple[str, ...]
    cache_hit: bool = False
    micro_strokes_suppressed: int = 0


_PIXEL_STROKE_CACHE: OrderedDict[tuple[str, str, str], tuple[np.ndarray, ...]] = (
    OrderedDict()
)
_PIXEL_STROKE_CACHE_LIMIT = 64


def vectorize_image(
    image: PreprocessedImage,
    options: Mapping[str, object],
    *,
    mode: str = "auto",
    width_mm: float,
    height_mm: float,
    element_id: str | None = None,
    source_path: str | None = None,
) -> VectorizedImage:
    selected = choose_vector_mode(image) if mode == "auto" else mode
    if selected not in {"outline", "centerline", "hatching"}:
        raise ValueError(f"Unknown image vectorization mode: {mode}")
    vector = options.get("vector", {})
    if not isinstance(vector, Mapping):
        raise TypeError("images.vector must be a mapping")
    tolerance_mm = float(vector.get("simplify_tolerance_mm", 0.08))
    scale = max(
        image.working_size[0] / max(width_mm, 1e-9),
        image.working_size[1] / max(height_mm, 1e-9),
    )
    tolerance_px = max(0.0, tolerance_mm * scale)
    edge = options.get("edge", {})
    if not isinstance(edge, Mapping):
        raise TypeError("images.edge must be a mapping")
    image_digest = hashlib.sha256()
    image_digest.update(image.grayscale.tobytes())
    image_digest.update(image.binary.tobytes())
    hatching = options.get("hatching", {})
    if not isinstance(hatching, Mapping):
        raise TypeError("images.hatching must be a mapping")
    mode_key = json.dumps(
        {"edge": dict(edge), "hatching": dict(hatching)},
        sort_keys=True,
        separators=(",", ":"),
    )
    cache_key = (image_digest.hexdigest(), selected, mode_key)
    cache_hit = cache_key in _PIXEL_STROKE_CACHE
    if cache_hit:
        cached = _PIXEL_STROKE_CACHE.pop(cache_key)
        _PIXEL_STROKE_CACHE[cache_key] = cached
        pixel_strokes = list(cached)
    else:
        if selected == "outline":
            edges = canny(
                image.grayscale,
                sigma=float(edge.get("sigma", 1.2)),
                low_threshold=float(edge.get("low_threshold", 0.08)),
                high_threshold=float(edge.get("high_threshold", 0.20)),
            )
            pixel_strokes = [contour[:, ::-1] for contour in find_contours(edges, 0.5)]
        elif selected == "centerline":
            pixel_strokes = _trace_skeleton(skeletonize(image.binary))
        else:
            pixel_strokes = _trace_hatching(
                image.grayscale,
                spacing_px=max(1.0, float(hatching.get("spacing_mm", 1.2)) * scale),
                levels=max(1, min(8, int(hatching.get("levels", 4)))),
                min_feature_px=max(
                    1,
                    round(float(hatching.get("min_feature_size_mm", 0.4)) * scale),
                ),
            )
        _PIXEL_STROKE_CACHE[cache_key] = tuple(pixel_strokes)
        if len(_PIXEL_STROKE_CACHE) > _PIXEL_STROKE_CACHE_LIMIT:
            _PIXEL_STROKE_CACHE.popitem(last=False)
    strokes: list[PlotterStroke] = []
    minimum_length = float(vector.get("min_stroke_length_mm", 0.35))
    sx = width_mm / max(1, image.working_size[0] - 1)
    sy = height_mm / max(1, image.working_size[1] - 1)
    micro_strokes_suppressed = 0
    for raw in pixel_strokes:
        simplified = approximate_polygon(np.asarray(raw), tolerance=tolerance_px)
        points = [Point(float(point[0]) * sx, float(point[1]) * sy) for point in simplified]
        points = _deduplicate(points)
        if len(points) < 2 or _length(points) < minimum_length:
            micro_strokes_suppressed += 1
            continue
        strokes.append(PlotterStroke(
            len(strokes), points, False, source_chars="", segment_types=(f"image-{selected}",),
            element_id=element_id, element_type="raster-image", source_path=source_path,
        ))
    max_strokes = int(vector.get("max_strokes_per_image", 10000))
    max_points = int(vector.get("max_points_per_image", 100000))
    point_count = sum(len(stroke.points) for stroke in strokes)
    if len(strokes) > max_strokes or point_count > max_points:
        raise ValueError(
            "Vectorized image exceeds safe complexity limits: "
            f"{len(strokes)} strokes, {point_count} points"
        )
    warnings = list(image.warnings)
    if not strokes and "blank_image" not in warnings:
        warnings.append("image_produced_no_strokes")
    return VectorizedImage(
        tuple(strokes),
        selected,
        point_count,
        tuple(warnings),
        cache_hit,
        micro_strokes_suppressed,
    )


def choose_vector_mode(image: PreprocessedImage) -> str:
    gray = image.grayscale
    quantized_levels = len(np.unique((gray * 31).astype(np.uint8)))
    foreground_ratio = float(image.binary.mean())
    white_ratio = float((gray > 0.94).mean())
    edge_density = float(canny(gray, sigma=1.0).mean())
    is_line_art = (
        quantized_levels <= 8
        or (white_ratio >= 0.72 and foreground_ratio <= 0.28 and edge_density <= 0.18)
    )
    return "centerline" if is_line_art else "outline"


def _trace_skeleton(mask: np.ndarray) -> list[np.ndarray]:
    pixels = {tuple(map(int, item)) for item in np.argwhere(mask)}
    if not pixels:
        return []
    neighbors: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for row, col in pixels:
        adjacent = sorted(
            (row + dr, col + dc)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc) and (row + dr, col + dc) in pixels
        )
        neighbors[(row, col)] = adjacent
    visited: set[frozenset[tuple[int, int]]] = set()
    paths: list[np.ndarray] = []

    def trace(start: tuple[int, int], nxt: tuple[int, int]) -> list[tuple[int, int]]:
        path = [start, nxt]
        visited.add(frozenset((start, nxt)))
        previous, current = start, nxt
        while len(neighbors[current]) == 2:
            candidate = next(point for point in neighbors[current] if point != previous)
            edge = frozenset((current, candidate))
            if edge in visited:
                break
            visited.add(edge)
            path.append(candidate)
            previous, current = current, candidate
        return path

    terminals = sorted(point for point, values in neighbors.items() if len(values) != 2)
    for start in terminals:
        for nxt in neighbors[start]:
            if frozenset((start, nxt)) not in visited:
                paths.append(np.asarray([(col, row) for row, col in trace(start, nxt)]))
    for start in sorted(pixels):
        for nxt in neighbors[start]:
            if frozenset((start, nxt)) not in visited:
                paths.append(np.asarray([(col, row) for row, col in trace(start, nxt)]))
    return paths


def _trace_hatching(
    grayscale: np.ndarray,
    *,
    spacing_px: float,
    levels: int,
    min_feature_px: int,
) -> list[np.ndarray]:
    height, width = grayscale.shape
    row_step = max(1, round(spacing_px / levels))
    paths: list[np.ndarray] = []
    for row_index, row in enumerate(range(0, height, row_step)):
        phase = row_index % levels
        darkness_threshold = (phase + 1) / (levels + 1)
        active = (1.0 - grayscale[row]) >= darkness_threshold
        start: int | None = None
        for column in range(width + 1):
            enabled = column < width and bool(active[column])
            if enabled and start is None:
                start = column
            elif not enabled and start is not None:
                if column - start >= min_feature_px:
                    paths.append(np.asarray(((start, row), (column - 1, row)), dtype=float))
                start = None
    return paths


def _deduplicate(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result


def _length(points: list[Point]) -> float:
    return sum(math.dist((a.x, a.y), (b.x, b.y)) for a, b in pairwise(points))
