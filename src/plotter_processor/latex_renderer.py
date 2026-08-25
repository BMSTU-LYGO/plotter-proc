from __future__ import annotations

import base64
import io
import json
import math
import os
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path
from typing import Protocol

os.environ.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")

import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser
from matplotlib.path import Path as MatplotlibPath
from matplotlib.textpath import TextPath
from PIL import Image

from plotter_processor.math_expression import (
    MathExpression,
    normalize_latex_expression,
    require_renderable,
)
from plotter_processor.models import PlotterStroke, Point
from plotter_processor.raster_centerline import (
    RasterCenterlineConfig,
    raster_to_centerline,
)

PT_TO_MM = 25.4 / 72.0
_RENDER_CACHE: OrderedDict[tuple[object, ...], RenderedMath] = OrderedDict()
_RENDER_CACHE_LIMIT = 128


@dataclass(frozen=True, slots=True)
class MathMetrics:
    width_mm: float
    height_mm: float
    baseline_mm: float


@dataclass(frozen=True, slots=True)
class MathRenderRequest:
    expression: str
    size_mm: float
    stroke_mode: str = "centerline"
    source_kind: str = "semantic-latex"


@dataclass(frozen=True, slots=True)
class RenderedMath:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float
    stroke_mode: str = "outline"
    source_kind: str = "semantic-latex"
    quality: dict[str, object] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    debug_mask: np.ndarray | None = field(default=None, repr=False, compare=False)
    debug_skeleton: np.ndarray | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class MathLayoutElement:
    expression: str
    strokes: tuple[PlotterStroke, ...]
    width_mm: float
    height_mm: float
    baseline_mm: float
    display_mode: bool


class MathRenderer(Protocol):
    def measure(self, expression: str | MathExpression, size_mm: float) -> MathMetrics: ...

    def render(self, expression: str | MathExpression, size_mm: float) -> RenderedMath: ...


class MathTextRenderer:
    def __init__(
        self,
        *,
        stroke_mode: str = "centerline",
        curve_tolerance_mm: float = 0.04,
        render_ppmm: float = 24.0,
        supersample: int = 2,
        threshold: int = 160,
        closing_radius_px: int = 1,
        min_component_length_mm: float = 0.20,
        max_render_pixels: int = 16_000_000,
        max_components: int = 5_000,
        max_points: int = 150_000,
        fallback_to_outline: bool = False,
        strict_quality: bool = False,
        source_kind: str = "semantic-latex",
    ) -> None:
        if stroke_mode not in {"centerline", "outline"}:
            raise ValueError(f"Unknown LaTeX stroke mode: {stroke_mode}")
        if curve_tolerance_mm <= 0 or not math.isfinite(curve_tolerance_mm):
            raise ValueError("latex.curve_tolerance_mm must be finite and positive")
        if render_ppmm <= 0 or not math.isfinite(render_ppmm):
            raise ValueError("latex.render_ppmm must be finite and positive")
        if supersample < 1:
            raise ValueError("latex.supersample must be positive")
        if not 0 <= threshold <= 255:
            raise ValueError("latex.threshold must be between 0 and 255")
        self.stroke_mode = stroke_mode
        self.curve_tolerance_mm = curve_tolerance_mm
        self.render_ppmm = render_ppmm
        self.supersample = supersample
        self.threshold = threshold
        self.closing_radius_px = closing_radius_px
        self.min_component_length_mm = min_component_length_mm
        self.max_render_pixels = max_render_pixels
        self.max_components = max_components
        self.max_points = max_points
        self.fallback_to_outline = fallback_to_outline
        self.strict_quality = strict_quality
        self.source_kind = source_kind
        self.cache_hits = 0
        self.cache_misses = 0

    def measure(self, expression: str | MathExpression, size_mm: float) -> MathMetrics:
        rendered = self.render(expression, size_mm)
        return MathMetrics(rendered.width_mm, rendered.height_mm, rendered.baseline_mm)

    def render(self, expression: str | MathExpression, size_mm: float) -> RenderedMath:
        model = (
            expression
            if isinstance(expression, MathExpression)
            else normalize_latex_expression(expression, source_syntax=self.source_kind)
        )
        require_renderable(model)
        expression_text = model.normalized
        if size_mm <= 0 or not math.isfinite(size_mm):
            raise ValueError("Formula size must be finite and positive")
        key = (
            expression_text,
            round(size_mm, 9),
            self.stroke_mode,
            self.curve_tolerance_mm,
            self.render_ppmm,
            self.supersample,
            self.threshold,
            self.closing_radius_px,
            self.min_component_length_mm,
            self.max_render_pixels,
            self.max_components,
            self.max_points,
            self.fallback_to_outline,
            self.strict_quality,
            self.source_kind,
        )
        if key in _RENDER_CACHE:
            self.cache_hits += 1
            rendered = _RENDER_CACHE.pop(key)
            _RENDER_CACHE[key] = rendered
            return rendered
        self.cache_misses += 1
        if self.stroke_mode == "outline":
            rendered = self._render_outline(expression_text, size_mm)
        else:
            try:
                rendered = self._render_centerline(expression_text, size_mm)
            except ValueError as error:
                if not self.fallback_to_outline:
                    raise
                rendered = replace(
                    self._render_outline(expression_text, size_mm),
                    warnings=("latex_centerline_outline_fallback", str(error)),
                    quality={"needs_review": True, "outline_fallback": True},
                )
        _RENDER_CACHE[key] = rendered
        if len(_RENDER_CACHE) > _RENDER_CACHE_LIMIT:
            _RENDER_CACHE.popitem(last=False)
        return rendered

    def _render_outline(self, expression: str, size_mm: float) -> RenderedMath:
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
            stroke.semantic_role = "latex-outline"
            stroke.source_chars = expression
            stroke.segment_types = ("latex-outline",)
        return RenderedMath(
            expression, tuple(strokes), width, height, baseline,
            "outline", self.source_kind,
            {
                "strokes": len(strokes),
                "points": sum(len(stroke.points) for stroke in strokes),
                "needs_review": False,
            },
        )

    def _render_centerline(self, expression: str, size_mm: float) -> RenderedMath:
        normalized = " ".join(expression.split())
        pixels_per_mm = self.render_ppmm * self.supersample
        dpi = pixels_per_mm * 25.4
        try:
            parsed = MathTextParser("agg").parse(
                f"${normalized}$",
                dpi=dpi,
                prop=FontProperties(size=size_mm / PT_TO_MM),
                antialiased=True,
            )
        except (RuntimeError, ValueError) as error:
            raise ValueError(f"MathText cannot render formula {expression!r}: {error}") from error
        grayscale = np.asarray(parsed.image, dtype=np.uint8)
        if grayscale.size > self.max_render_pixels:
            raise ValueError(
                f"MathText mask has {grayscale.size} pixels; limit is {self.max_render_pixels}"
            )
        padding = max(2, self.closing_radius_px + 1)
        grayscale = np.pad(grayscale, padding)
        mask = grayscale >= self.threshold
        geometry = raster_to_centerline(
            mask,
            1.0 / pixels_per_mm,
            RasterCenterlineConfig(
                threshold=self.threshold,
                closing_radius_px=self.closing_radius_px,
                min_component_length_mm=self.min_component_length_mm,
                simplify_tolerance_mm=self.curve_tolerance_mm,
                max_render_pixels=self.max_render_pixels,
                max_components=self.max_components,
                max_points=self.max_points,
                strict_quality=self.strict_quality,
            ),
        )
        strokes = [replace(stroke) for stroke in geometry.strokes]
        for index, stroke in enumerate(strokes):
            stroke.id = index
            stroke.element_type = "latex"
            stroke.semantic_role = "latex-centerline"
            stroke.source_chars = expression
            stroke.segment_types = ("latex-centerline",)
        return RenderedMath(
            expression,
            tuple(strokes),
            grayscale.shape[1] / pixels_per_mm,
            grayscale.shape[0] / pixels_per_mm,
            (float(parsed.height) - float(parsed.depth) + padding) / pixels_per_mm,
            "centerline",
            self.source_kind,
            geometry.quality,
            geometry.warnings,
            geometry.mask,
            geometry.skeleton,
        )


def math_renderer_from_options(
    options: Mapping[str, object],
    *,
    stroke_mode: str | None = None,
    strict_quality: bool | None = None,
    source_kind: str = "semantic-latex",
) -> MathTextRenderer:
    resolved_mode = stroke_mode or str(options.get("stroke_mode", "centerline"))
    resolved_strict = (
        bool(options.get("strict_quality", False))
        if strict_quality is None
        else strict_quality
    )
    return MathTextRenderer(
        stroke_mode=resolved_mode,
        curve_tolerance_mm=float(options.get("curve_tolerance_mm", 0.04)),
        render_ppmm=float(options.get("render_ppmm", 24.0)),
        supersample=int(options.get("supersample", 2)),
        threshold=int(options.get("threshold", 160)),
        closing_radius_px=int(options.get("closing_radius_px", 1)),
        min_component_length_mm=float(options.get("min_component_length_mm", 0.20)),
        max_render_pixels=int(options.get("max_render_pixels", 16_000_000)),
        max_components=int(options.get("max_components", 5_000)),
        max_points=int(options.get("max_points", 150_000)),
        fallback_to_outline=bool(options.get("fallback_to_outline", False)),
        strict_quality=resolved_strict,
        source_kind=source_kind,
    )


def render_visual_math_image(
    image_path: Path,
    expression_label: str,
    pixels_per_mm: float,
    options: Mapping[str, object],
    *,
    strict_quality: bool = False,
) -> RenderedMath:
    if pixels_per_mm <= 0 or not math.isfinite(pixels_per_mm):
        raise ValueError("PDF math pixels_per_mm must be finite and positive")
    try:
        with Image.open(image_path) as image:
            grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
    except OSError as error:
        raise ValueError(f"Cannot read PDF visual math image: {image_path}") from error
    threshold = int(options.get("threshold", 160))
    mask = grayscale <= threshold
    geometry = raster_to_centerline(
        mask,
        1.0 / pixels_per_mm,
        RasterCenterlineConfig(
            threshold=threshold,
            closing_radius_px=int(options.get("closing_radius_px", 1)),
            min_component_length_mm=float(options.get("min_component_length_mm", 0.20)),
            simplify_tolerance_mm=float(options.get("curve_tolerance_mm", 0.04)),
            max_render_pixels=int(options.get("max_render_pixels", 16_000_000)),
            max_components=int(options.get("max_components", 5_000)),
            max_points=int(options.get("max_points", 150_000)),
            strict_quality=strict_quality,
        ),
    )
    strokes = [replace(stroke) for stroke in geometry.strokes]
    for index, stroke in enumerate(strokes):
        stroke.id = index
        stroke.element_type = "latex"
        stroke.semantic_role = "latex-centerline"
        stroke.source_chars = expression_label
        stroke.segment_types = ("latex-centerline",)
    height = grayscale.shape[0] / pixels_per_mm
    return RenderedMath(
        expression_label,
        tuple(strokes),
        grayscale.shape[1] / pixels_per_mm,
        height,
        height * 0.75,
        "centerline",
        "pdf-visual",
        geometry.quality,
        geometry.warnings,
        geometry.mask,
        geometry.skeleton,
    )


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
        rendered.stroke_mode, rendered.source_kind, rendered.quality,
        rendered.warnings, rendered.debug_mask, rendered.debug_skeleton,
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
        "stroke_mode": rendered.stroke_mode,
        "source_kind": rendered.source_kind,
        "quality": rendered.quality,
        "warnings": list(rendered.warnings),
    }
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prefix = svg.with_suffix("")
    Path(f"{prefix}-source.json").write_text(
        json.dumps(
            {
                "formula_index": formula_index,
                "expression": rendered.expression,
                "display_mode": display_mode,
                "source_syntax": source_syntax,
                "stroke_mode": rendered.stroke_mode,
                "source_kind": rendered.source_kind,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    centerline_svg = Path(f"{prefix}-centerline.svg")
    centerline_svg.write_text(svg.read_text(encoding="utf-8"), encoding="utf-8")
    graph_lines = _debug_svg_lines(rendered, stroke_color="#1b4dff", show_nodes=True)
    Path(f"{prefix}-graph.svg").write_text("\n".join(graph_lines) + "\n", encoding="utf-8")
    if rendered.debug_mask is not None:
        mask_image = _binary_debug_image(rendered.debug_mask)
        mask_image.save(Path(f"{prefix}-mask.png"), format="PNG")
        if rendered.debug_skeleton is not None:
            _binary_debug_image(rendered.debug_skeleton).save(
                Path(f"{prefix}-skeleton.png"), format="PNG"
            )
        Path(f"{prefix}-overlay.svg").write_text(
            _overlay_svg(rendered, mask_image), encoding="utf-8"
        )


def _debug_svg_lines(
    rendered: RenderedMath, *, stroke_color: str, show_nodes: bool
) -> list[str]:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {rendered.width_mm} {rendered.height_mm}">',
        '<rect width="100%" height="100%" fill="white"/>',
        (
            f'<line x1="0" y1="{rendered.baseline_mm}" x2="{rendered.width_mm}" '
            f'y2="{rendered.baseline_mm}" stroke="#999" stroke-dasharray="0.4 0.4"/>'
        ),
    ]
    for stroke in rendered.strokes:
        points = " ".join(f"{point.x:.5f},{point.y:.5f}" for point in stroke.points)
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="{stroke_color}" '
            'stroke-width="0.08"/>'
        )
        if show_nodes and stroke.points:
            for point in (stroke.points[0], stroke.points[-1]):
                lines.append(
                    f'<circle cx="{point.x:.5f}" cy="{point.y:.5f}" r="0.10" fill="#ff8c00"/>'
                )
    lines.append("</svg>")
    return lines


def _binary_debug_image(mask: np.ndarray) -> Image.Image:
    pixels = np.where(mask, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels, mode="L")


def _overlay_svg(rendered: RenderedMath, mask_image: Image.Image) -> str:
    buffer = io.BytesIO()
    mask_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {rendered.width_mm} {rendered.height_mm}">',
        (
            f'<image href="data:image/png;base64,{encoded}" x="0" y="0" '
            f'width="{rendered.width_mm}" height="{rendered.height_mm}" opacity="0.35"/>'
        ),
        (
            f'<rect x="0" y="0" width="{rendered.width_mm}" height="{rendered.height_mm}" '
            'fill="none" stroke="#555" stroke-width="0.05"/>'
        ),
        (
            f'<line x1="0" y1="{rendered.baseline_mm}" x2="{rendered.width_mm}" '
            f'y2="{rendered.baseline_mm}" stroke="#0080ff" stroke-dasharray="0.4 0.4"/>'
        ),
    ]
    for index, stroke in enumerate(rendered.strokes):
        points = " ".join(f"{point.x:.5f},{point.y:.5f}" for point in stroke.points)
        lines.append(
            f'<polyline data-component-id="{index}" points="{points}" fill="none" '
            'stroke="#e00030" stroke-width="0.10"/>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


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
