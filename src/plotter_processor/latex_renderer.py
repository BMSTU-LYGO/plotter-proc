from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import Protocol

os.environ.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")

from matplotlib.path import Path as MatplotlibPath
from matplotlib.textpath import TextPath

from plotter_processor.models import PlotterStroke, Point

PT_TO_MM = 25.4 / 72.0


@dataclass(frozen=True, slots=True)
class MathMetrics:
    width_mm: float
    height_mm: float
    baseline_mm: float


@dataclass(frozen=True, slots=True)
class RenderedMath:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float


@dataclass(frozen=True, slots=True)
class MathLayoutElement:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float
    display_mode: bool


class MathRenderer(Protocol):
    def measure(self, expression: str, size_mm: float) -> MathMetrics: ...

    def render(self, expression: str, size_mm: float) -> RenderedMath: ...


class MathTextRenderer:
    def __init__(self, *, curve_tolerance_mm: float = 0.04) -> None:
        if curve_tolerance_mm <= 0 or not math.isfinite(curve_tolerance_mm):
            raise ValueError("latex.curve_tolerance_mm must be finite and positive")
        self.curve_tolerance_mm = curve_tolerance_mm

    def measure(self, expression: str, size_mm: float) -> MathMetrics:
        rendered = self.render(expression, size_mm)
        return MathMetrics(rendered.width_mm, rendered.height_mm, rendered.baseline_mm)

    def render(self, expression: str, size_mm: float) -> RenderedMath:
        if not expression.strip():
            raise ValueError("Cannot render an empty LaTeX formula")
        if size_mm <= 0 or not math.isfinite(size_mm):
            raise ValueError("Formula size must be finite and positive")
        mathtext_expression = " ".join(expression.split())
        try:
            path = TextPath(
                (0, 0), f"${mathtext_expression}$", size=size_mm / PT_TO_MM, usetex=False
            )
        except (RuntimeError, ValueError) as error:
            raise ValueError(f"MathText cannot render formula {expression!r}: {error}") from error
        vertices = path.vertices
        codes = path.codes
        if len(vertices) == 0 or codes is None:
            raise ValueError(f"MathText produced no vector path for formula {expression!r}")
        min_x = float(vertices[:, 0].min())
        max_x = float(vertices[:, 0].max())
        min_y = float(vertices[:, 1].min())
        max_y = float(vertices[:, 1].max())
        strokes = _path_to_strokes(
            vertices, codes, min_x=min_x, max_y=max_y,
            tolerance_pt=self.curve_tolerance_mm / PT_TO_MM,
        )
        width = max((max_x - min_x) * PT_TO_MM, 0.01)
        height = max((max_y - min_y) * PT_TO_MM, 0.01)
        baseline = max_y * PT_TO_MM
        for index, stroke in enumerate(strokes):
            stroke.id = index
            stroke.element_type = "latex"
            stroke.source_chars = expression
            stroke.segment_types = ("latex-outline",)
        return RenderedMath(expression, tuple(strokes), width, height, baseline)


def scale_rendered_math(rendered: RenderedMath, scale: float) -> RenderedMath:
    if scale <= 0:
        raise ValueError("Formula scale must be positive")
    strokes = tuple(
        replace(
            stroke,
            points=[Point(point.x * scale, point.y * scale) for point in stroke.points],
        )
        for stroke in rendered.strokes
    )
    return RenderedMath(
        rendered.expression, strokes, rendered.width_mm * scale,
        rendered.height_mm * scale, rendered.baseline_mm * scale,
    )


def export_latex_debug(
    rendered: RenderedMath,
    svg_path: str | Path,
    json_path: str | Path,
    *,
    formula_index: int,
    display_mode: bool,
    source_syntax: str,
) -> None:
    svg = Path(svg_path)
    data = Path(json_path)
    svg.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
            f'{rendered.width_mm} {rendered.height_mm}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for stroke in rendered.strokes:
        points = " ".join(f"{point.x:.5f},{point.y:.5f}" for point in stroke.points)
        tag = "polygon" if stroke.closed else "polyline"
        lines.append(f'<{tag} points="{points}" fill="none" stroke="black" stroke-width="0.08"/>')
    lines.append("</svg>")
    svg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "formula_index": formula_index,
        "expression": rendered.expression,
        "display_mode": display_mode,
        "source_syntax": source_syntax,
        "width_mm": rendered.width_mm,
        "height_mm": rendered.height_mm,
        "baseline_mm": rendered.baseline_mm,
        "strokes": len(rendered.strokes),
        "points": sum(len(stroke.points) for stroke in rendered.strokes),
    }
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _path_to_strokes(
    vertices: object,
    codes: object,
    *,
    min_x: float,
    max_y: float,
    tolerance_pt: float,
) -> list[PlotterStroke]:
    strokes: list[PlotterStroke] = []
    current: list[tuple[float, float]] = []
    cursor = (0.0, 0.0)

    def finish(closed: bool = False) -> None:
        nonlocal current
        points = _dedupe([
            Point((x - min_x) * PT_TO_MM, (max_y - y) * PT_TO_MM)
            for x, y in current
        ])
        if closed and len(points) > 1 and points[-1] == points[0]:
            points.pop()
        minimum = 3 if closed else 2
        if len({(point.x, point.y) for point in points}) >= minimum:
            strokes.append(PlotterStroke(len(strokes), points, closed))
        current = []

    index = 0
    while index < len(codes):
        code = int(codes[index])
        vertex = (float(vertices[index][0]), float(vertices[index][1]))
        if code == MatplotlibPath.MOVETO:
            finish()
            current = [vertex]
            cursor = vertex
            index += 1
        elif code == MatplotlibPath.LINETO:
            current.append(vertex)
            cursor = vertex
            index += 1
        elif code == MatplotlibPath.CURVE3:
            if index + 1 >= len(codes):
                raise ValueError("Invalid quadratic MathText path")
            control = vertex
            end = (float(vertices[index + 1][0]), float(vertices[index + 1][1]))
            current.extend(_flatten_quadratic(cursor, control, end, tolerance_pt)[1:])
            cursor = end
            index += 2
        elif code == MatplotlibPath.CURVE4:
            if index + 2 >= len(codes):
                raise ValueError("Invalid cubic MathText path")
            control1 = vertex
            control2 = (float(vertices[index + 1][0]), float(vertices[index + 1][1]))
            end = (float(vertices[index + 2][0]), float(vertices[index + 2][1]))
            current.extend(_flatten_cubic(cursor, control1, control2, end, tolerance_pt)[1:])
            cursor = end
            index += 3
        elif code == MatplotlibPath.CLOSEPOLY:
            finish(True)
            index += 1
        else:
            raise ValueError(f"Unsupported MathText path command: {code}")
    finish()
    return strokes


def _flatten_quadratic(
    start: tuple[float, float], control: tuple[float, float], end: tuple[float, float], tolerance: float
) -> list[tuple[float, float]]:
    steps = _curve_steps((start, control, end), tolerance)
    return [
        (
            (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t * t * end[0],
            (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t * t * end[1],
        )
        for t in (index / steps for index in range(steps + 1))
    ]


def _flatten_cubic(
    start: tuple[float, float], control1: tuple[float, float],
    control2: tuple[float, float], end: tuple[float, float], tolerance: float,
) -> list[tuple[float, float]]:
    steps = _curve_steps((start, control1, control2, end), tolerance)
    return [
        (
            (1 - t) ** 3 * start[0] + 3 * (1 - t) ** 2 * t * control1[0]
            + 3 * (1 - t) * t * t * control2[0] + t**3 * end[0],
            (1 - t) ** 3 * start[1] + 3 * (1 - t) ** 2 * t * control1[1]
            + 3 * (1 - t) * t * t * control2[1] + t**3 * end[1],
        )
        for t in (index / steps for index in range(steps + 1))
    ]


def _curve_steps(points: tuple[tuple[float, float], ...], tolerance: float) -> int:
    polygon = sum(math.dist(left, right) for left, right in pairwise(points))
    return max(4, min(64, math.ceil(polygon / max(tolerance * 4, 0.01))))


def _dedupe(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or math.dist((point.x, point.y), (result[-1].x, result[-1].y)) > 1e-9:
            result.append(point)
    return result
