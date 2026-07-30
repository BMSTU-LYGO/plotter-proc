from __future__ import annotations

import math
from dataclasses import dataclass

from fontTools.pens.basePen import BasePen

from plotter_processor.models import Point


@dataclass(slots=True)
class FlattenedContour:
    points: list[Point]
    closed: bool


class CurveFlatteningPen(BasePen):
    def __init__(
        self,
        glyph_set: object,
        *,
        tolerance_mm: float = 0.08,
        min_segment_length_mm: float = 0.03,
        max_points_per_contour: int = 5000,
        max_recursion_depth: int = 20,
    ) -> None:
        super().__init__(glyph_set)
        if tolerance_mm <= 0 or min_segment_length_mm < 0:
            raise ValueError("Curve tolerances must be positive")
        if max_points_per_contour < 2 or max_recursion_depth < 0:
            raise ValueError("Curve limits are invalid")
        self.tolerance = tolerance_mm
        self.min_segment = min_segment_length_mm
        self.max_points = max_points_per_contour
        self.max_depth = max_recursion_depth
        self.contours: list[FlattenedContour] = []
        self.warnings: list[str] = []
        self._points: list[Point] | None = None

    def _moveTo(self, point: tuple[float, float]) -> None:
        if self._points is not None:
            self._finish(False)
        self._points = []
        self._append(point, force=True)

    def _lineTo(self, point: tuple[float, float]) -> None:
        self._append(point)

    def _qCurveToOne(self, control: tuple[float, float], point: tuple[float, float]) -> None:
        start = self._current()
        self._flatten_quadratic(start, control, point, 0)

    def _curveToOne(
        self,
        control1: tuple[float, float],
        control2: tuple[float, float],
        point: tuple[float, float],
    ) -> None:
        start = self._current()
        self._flatten_cubic(start, control1, control2, point, 0)

    def _closePath(self) -> None:
        self._finish(True)

    def _endPath(self) -> None:
        self._finish(False)

    def _finish(self, closed: bool) -> None:
        if self._points is None:
            return
        if closed and len(self._points) > 1 and self._points[-1] == self._points[0]:
            self._points.pop()
        self.contours.append(FlattenedContour(self._points, closed))
        self._points = None

    def _current(self) -> tuple[float, float]:
        if not self._points:
            raise ValueError("Curve command received before moveTo")
        point = self._points[-1]
        return point.x, point.y

    def _append(self, value: tuple[float, float], *, force: bool = False) -> None:
        if self._points is None:
            raise ValueError("Point command received before moveTo")
        x, y = float(value[0]), float(value[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Font outline contains NaN or infinite coordinates")
        point = Point(x, y)
        if self._points and not force:
            distance = math.hypot(point.x - self._points[-1].x, point.y - self._points[-1].y)
            if distance < self.min_segment:
                return
        if len(self._points) >= self.max_points:
            if "Maximum points per contour reached" not in self.warnings:
                self.warnings.append("Maximum points per contour reached")
            self._points[-1] = point
            return
        self._points.append(point)

    def _flatten_quadratic(
        self, p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], depth: int
    ) -> None:
        if depth >= self.max_depth or _distance_to_chord(p1, p0, p2) <= self.tolerance:
            if (
                depth >= self.max_depth
                and "Maximum curve recursion depth reached" not in self.warnings
            ):
                self.warnings.append("Maximum curve recursion depth reached")
            self._append(p2)
            return
        p01, p12 = _midpoint(p0, p1), _midpoint(p1, p2)
        middle = _midpoint(p01, p12)
        self._flatten_quadratic(p0, p01, middle, depth + 1)
        self._flatten_quadratic(middle, p12, p2, depth + 1)

    def _flatten_cubic(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
        depth: int,
    ) -> None:
        flatness = max(_distance_to_chord(p1, p0, p3), _distance_to_chord(p2, p0, p3))
        if depth >= self.max_depth or flatness <= self.tolerance:
            if (
                depth >= self.max_depth
                and "Maximum curve recursion depth reached" not in self.warnings
            ):
                self.warnings.append("Maximum curve recursion depth reached")
            self._append(p3)
            return
        p01, p12, p23 = _midpoint(p0, p1), _midpoint(p1, p2), _midpoint(p2, p3)
        p012, p123 = _midpoint(p01, p12), _midpoint(p12, p23)
        middle = _midpoint(p012, p123)
        self._flatten_cubic(p0, p01, p012, middle, depth + 1)
        self._flatten_cubic(middle, p123, p23, p3, depth + 1)


def _midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _distance_to_chord(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / length
