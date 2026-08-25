from __future__ import annotations

import math
import re
from pathlib import Path
from xml.etree import ElementTree

from fontTools.pens.transformPen import TransformPen
from fontTools.svgLib.path import parse_path

from plotter_processor.curve_flattener import CurveFlatteningPen
from plotter_processor.models import PlotterStroke

SUPPORTED = {"svg", "g", "path", "line", "polyline", "polygon", "rect", "circle", "ellipse"}
FORBIDDEN = {"script", "foreignObject", "image", "text", "use", "filter", "style", "animate", "animateTransform"}
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
PX_TO_MM = 25.4 / 96.0


def import_svg(
    path: Path,
    *,
    x_mm: float,
    y_mm: float,
    width_mm: float,
    height_mm: float,
    fit: str = "contain",
    element_id: str | None = None,
    max_file_bytes: int = 2_000_000,
    max_nodes: int = 10_000,
    max_points: int = 100_000,
) -> list[PlotterStroke]:
    data = path.read_bytes()
    if len(data) > max_file_bytes:
        raise ValueError("SVG exceeds safe file size limit")
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("SVG entities and DOCTYPE are forbidden")
    root = ElementTree.fromstring(data)
    nodes = list(root.iter())
    if len(nodes) > max_nodes:
        raise ValueError("SVG exceeds safe XML node limit")
    _validate_tree(nodes)
    viewbox = _viewbox(root)
    target = _fit_matrix(viewbox, x_mm, y_mm, width_mm, height_mm, fit)
    strokes: list[PlotterStroke] = []
    _walk(root, target, strokes, element_id, depth=0)
    if not strokes:
        raise ValueError("SVG contains no supported line-art geometry")
    if sum(len(stroke.points) for stroke in strokes) > max_points:
        raise ValueError("SVG exceeds safe flattened point limit")
    return strokes


def svg_intrinsic_size_mm(path: Path) -> tuple[float, float]:
    data = path.read_bytes()
    if len(data) > 2_000_000:
        raise ValueError("SVG exceeds safe file size limit")
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("SVG entities and DOCTYPE are forbidden")
    root = ElementTree.fromstring(data)
    viewbox = _viewbox(root)
    width = _svg_length_mm(root.attrib.get("width"))
    height = _svg_length_mm(root.attrib.get("height"))
    if width is None or height is None:
        width = viewbox[2] * PX_TO_MM
        height = viewbox[3] * PX_TO_MM
    if width <= 0 or height <= 0:
        raise ValueError("SVG intrinsic dimensions must be positive")
    return width, height


def _validate_tree(nodes: list[ElementTree.Element]) -> None:
    for node in nodes:
        name = _local(node.tag)
        if name in FORBIDDEN:
            raise ValueError(f"Unsafe or unsupported SVG element: {name}")
        if name not in SUPPORTED:
            raise ValueError(f"Unsupported SVG element: {name}")
        for key, value in node.attrib.items():
            local = _local(key).lower()
            lowered = value.lower()
            if local.startswith("on") or "javascript:" in lowered or "file:" in lowered or "http:" in lowered or "https:" in lowered:
                raise ValueError(f"Unsafe SVG attribute: {key}")
        fill = node.attrib.get("fill", "none").lower()
        stroke = node.attrib.get("stroke")
        if name not in {"svg", "g"} and fill not in {"none", "transparent"} and stroke is None:
            raise ValueError("Filled-only SVG objects require explicit outline conversion")


def _walk(node, parent_matrix, output, element_id, depth: int) -> None:
    if depth > 64:
        raise ValueError("SVG group nesting exceeds safe limit")
    matrix = _multiply(parent_matrix, _parse_transform(node.attrib.get("transform", "")))
    name = _local(node.tag)
    if name not in {"svg", "g"}:
        contours = _contours(node, name, matrix)
        for contour in contours:
            if len(contour.points) >= (3 if contour.closed else 2):
                output.append(
                    PlotterStroke(
                        len(output), contour.points, contour.closed,
                        element_id=element_id,
                        element_type="svg-vector",
                        semantic_role="svg-vector",
                        source_chars="", segment_types=("svg",),
                    )
                )
    for child in node:
        _walk(child, matrix, output, element_id, depth + 1)


def _contours(node, name: str, matrix):
    pen = CurveFlatteningPen(None, tolerance_mm=0.05, min_segment_length_mm=0.001)
    transformed = TransformPen(pen, matrix)
    if name == "path":
        data = node.attrib.get("d", "")
        if len(data) > 1_000_000:
            raise ValueError("SVG path data exceeds safe limit")
        parse_path(data, transformed)
    else:
        points, closed = _basic_points(node, name)
        transformed.moveTo(points[0])
        for point in points[1:]:
            transformed.lineTo(point)
        transformed.closePath() if closed else transformed.endPath()
    return pen.contours


def _basic_points(node, name: str) -> tuple[list[tuple[float, float]], bool]:
    n = lambda key, default="0": _finite(node.attrib.get(key, default))
    if name == "line":
        return [(n("x1"), n("y1")), (n("x2"), n("y2"))], False
    if name in {"polyline", "polygon"}:
        values = [float(value) for value in re.findall(NUMBER, node.attrib.get("points", ""))]
        if len(values) < 4 or len(values) % 2:
            raise ValueError(f"Invalid SVG {name} points")
        return list(zip(values[::2], values[1::2], strict=True)), name == "polygon"
    if name == "rect":
        x, y, w, h = n("x"), n("y"), n("width"), n("height")
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True
    cx, cy = n("cx"), n("cy")
    rx = n("r") if name == "circle" else n("rx")
    ry = rx if name == "circle" else n("ry")
    return [
        (cx + rx * math.cos(2 * math.pi * index / 64), cy + ry * math.sin(2 * math.pi * index / 64))
        for index in range(64)
    ], True


def _viewbox(root) -> tuple[float, float, float, float]:
    values = [float(value) for value in re.findall(NUMBER, root.attrib.get("viewBox", ""))]
    if len(values) == 4 and values[2] > 0 and values[3] > 0:
        return tuple(values)  # type: ignore[return-value]
    width, height = root.attrib.get("width"), root.attrib.get("height")
    if width and height:
        return 0.0, 0.0, _finite(re.findall(NUMBER, width)[0]), _finite(re.findall(NUMBER, height)[0])
    raise ValueError("SVG requires viewBox or numeric width/height")


def _fit_matrix(viewbox, x, y, width, height, fit):
    if width <= 0 or height <= 0 or fit not in {"contain", "cover", "stretch"}:
        raise ValueError("Invalid SVG target box or fit mode")
    vx, vy, vw, vh = viewbox
    sx, sy = width / vw, height / vh
    if fit != "stretch":
        scale = min(sx, sy) if fit == "contain" else max(sx, sy)
        sx = sy = scale
    return sx, 0.0, 0.0, sy, x + (width - vw * sx) / 2 - vx * sx, y + (height - vh * sy) / 2 - vy * sy


def _parse_transform(value: str):
    result = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args_text in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value):
        args = [_finite(item) for item in re.findall(NUMBER, args_text)]
        if name == "translate" and 1 <= len(args) <= 2:
            item = (1, 0, 0, 1, args[0], args[1] if len(args) == 2 else 0)
        elif name == "scale" and 1 <= len(args) <= 2:
            item = (args[0], 0, 0, args[-1], 0, 0)
        elif name == "rotate" and len(args) == 1:
            angle = math.radians(args[0]); item = (math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle), 0, 0)
        elif name == "matrix" and len(args) == 6:
            item = tuple(args)
        else:
            raise ValueError(f"Invalid or unsupported SVG transform: {name}")
        result = _multiply(result, item)
    if value.strip() and not re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", value):
        raise ValueError("Invalid SVG transform")
    return result


def _multiply(a, b):
    return (
        a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
        a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
        a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
    )


def _finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("SVG contains NaN or Infinity")
    return number


def _svg_length_mm(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(rf"\s*({NUMBER})\s*(px|mm|cm|in|pt|pc)?\s*", value)
    if match is None:
        return None
    number = _finite(match.group(1))
    factor = {
        None: PX_TO_MM,
        "px": PX_TO_MM,
        "mm": 1.0,
        "cm": 10.0,
        "in": 25.4,
        "pt": 25.4 / 72.0,
        "pc": 25.4 / 6.0,
    }[match.group(2)]
    return number * factor


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
