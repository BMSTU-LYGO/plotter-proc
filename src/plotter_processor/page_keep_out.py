from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise

from plotter_processor.models import PageSpec, PathDocument, Point


@dataclass(frozen=True, slots=True)
class CircularKeepOut:
    x_mm: float
    y_mm: float
    radius_mm: float
    clearance_mm: float

    @property
    def safe_radius_mm(self) -> float:
        return self.radius_mm + self.clearance_mm

    def payload(self) -> dict[str, float]:
        return {**asdict(self), "safe_radius_mm": self.safe_radius_mm}


def resolve_keep_out_zones(
    holes: Sequence[Mapping[str, object]],
    clearance_mm: object,
    page: PageSpec,
) -> tuple[CircularKeepOut, ...]:
    clearance = _non_negative_value(clearance_mm, "hole_clearance_mm")
    zones: list[CircularKeepOut] = []
    for index, hole in enumerate(holes):
        x = _number(hole, "x_mm", index)
        y = _number(hole, "y_mm", index)
        radius = _positive(hole, "radius_mm", index)
        if not 0 <= x <= page.width_mm or not 0 <= y <= page.height_mm:
            raise ValueError(f"holes[{index}] center lies outside the physical page")
        zones.append(CircularKeepOut(x, y, radius, clearance))
    return tuple(zones)


def effective_content_margins(
    margins: Mapping[str, object],
    page: PageSpec,
    zones: Sequence[CircularKeepOut],
) -> dict[str, object]:
    effective = dict(margins)
    left = _margin(effective, "left")
    right = _margin(effective, "right")
    for zone in zones:
        if zone.x_mm <= page.width_mm / 2:
            left = max(left, zone.x_mm + zone.safe_radius_mm)
        else:
            right = max(right, page.width_mm - zone.x_mm + zone.safe_radius_mm)
    effective["left"] = left
    effective["right"] = right
    return effective


def validate_path_keep_outs(
    document: PathDocument,
    raw_zones: object,
    *,
    page_number: int = 1,
) -> None:
    if raw_zones is None:
        return
    if not isinstance(raw_zones, Sequence) or isinstance(raw_zones, (str, bytes)):
        raise TypeError("page_keep_out_zones must be a sequence")
    zones = [_canonical_zone(value, index) for index, value in enumerate(raw_zones)]
    for stroke in document.strokes:
        points = stroke.points
        segments = list(pairwise(points))
        if stroke.closed and points:
            segments.append((points[-1], points[0]))
        for start, end in segments:
            for zone in zones:
                if _segment_distance(start, end, zone.x_mm, zone.y_mm) <= (
                    zone.safe_radius_mm + 1e-9
                ):
                    element = stroke.element_id or f"stroke {stroke.id}"
                    raise ValueError(
                        f"Page {page_number}, element {element!r}: draw path intersects "
                        "a page hole keep-out zone"
                    )


def _canonical_zone(value: object, index: int) -> CircularKeepOut:
    if not isinstance(value, Mapping):
        raise TypeError(f"page_keep_out_zones[{index}] must be a mapping")
    return CircularKeepOut(
        _number(value, "x_mm", index),
        _number(value, "y_mm", index),
        _positive(value, "radius_mm", index),
        _non_negative_value(value.get("clearance_mm", 0.0), "clearance_mm"),
    )


def _segment_distance(start: Point, end: Point, x: float, y: float) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    squared = dx * dx + dy * dy
    if squared == 0:
        return math.hypot(start.x - x, start.y - y)
    ratio = max(0.0, min(1.0, ((x - start.x) * dx + (y - start.y) * dy) / squared))
    return math.hypot(start.x + ratio * dx - x, start.y + ratio * dy - y)


def _number(values: Mapping[str, object], key: str, index: int) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"holes[{index}].{key} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"holes[{index}].{key} must be finite")
    return number


def _positive(values: Mapping[str, object], key: str, index: int) -> float:
    number = _number(values, key, index)
    if number <= 0:
        raise ValueError(f"holes[{index}].{key} must be positive")
    return number


def _non_negative_value(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _margin(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid page margin: {key}")
    return float(value)
