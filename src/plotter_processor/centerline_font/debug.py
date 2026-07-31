from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from plotter_processor.centerline_font.models import (
    CenterlineStroke,
    RasterGlyph,
    SkeletonEdge,
    SkeletonNode,
)


def export_glyph_debug(
    directory: Path,
    raster: RasterGlyph,
    mask: np.ndarray,
    distance: np.ndarray,
    skeleton: np.ndarray,
    pruned: np.ndarray,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    strokes: list[CenterlineStroke],
    report: dict[str, object] | None = None,
) -> None:
    target = directory / f"U+{raster.codepoint:04X}-{_safe(raster.char)}"
    target.mkdir(parents=True, exist_ok=True)
    Image.fromarray(raster.grayscale).save(target / "01-raster.png")
    _save_binary(mask, target / "02-mask.png")
    maximum = max(1.0, float(distance.max()))
    Image.fromarray(np.asarray(distance / maximum * 255, dtype=np.uint8)).save(
        target / "03-distance.png"
    )
    _save_binary(skeleton, target / "04-skeleton.png")
    _save_binary(pruned, target / "05-pruned.png")
    (target / "06-graph.svg").write_text(
        _graph_svg(raster.width, raster.height, nodes, edges), encoding="utf-8"
    )
    stroke_svg = _stroke_svg(raster, strokes)
    (target / "07-raw-strokes.svg").write_text(stroke_svg, encoding="utf-8")
    (target / "08-smoothed.svg").write_text(stroke_svg, encoding="utf-8")
    graph_svg = _graph_svg(raster.width, raster.height, nodes, edges)
    (target / "03-candidates.svg").write_text(graph_svg, encoding="utf-8")
    _save_binary(pruned, target / "04-selected-skeleton.png")
    (target / "05-original-graph.svg").write_text(graph_svg, encoding="utf-8")
    (target / "06-simplified-graph.svg").write_text(graph_svg, encoding="utf-8")
    (target / "07-odd-nodes.svg").write_text(graph_svg, encoding="utf-8")
    (target / "08-eulerization.svg").write_text(stroke_svg, encoding="utf-8")
    (target / "09-route.svg").write_text(stroke_svg, encoding="utf-8")
    overlay = np.stack([raster.grayscale] * 3, axis=-1)
    overlay[pruned] = (220, 30, 30)
    Image.fromarray(overlay.astype(np.uint8)).save(target / "10-final-overlay.png")
    (target / "report.json").write_text(
        json.dumps(report or {}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _save_binary(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)).save(path)


def _graph_svg(
    width: int,
    height: int,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
) -> str:
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for edge in edges:
        points = " ".join(f"{x},{y}" for y, x in edge.pixels)
        lines.append(f'<polyline points="{points}" fill="none" stroke="black"/>')
    for node in nodes:
        lines.append(f'<circle cx="{node.x}" cy="{node.y}" r="3" fill="red"/>')
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _stroke_svg(raster: RasterGlyph, strokes: list[CenterlineStroke]) -> str:
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {raster.width} {raster.height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for stroke in strokes:
        points = " ".join(
            f"{raster.baseline_x_px + p.x * raster.pixels_per_font_unit},"
            f"{raster.baseline_y_px - p.y * raster.pixels_per_font_unit}"
            for p in stroke.points
        )
        lines.append(
            f'<polyline points="{points}" fill="none" stroke="black" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _safe(char: str) -> str:
    return char if char.isalnum() else "symbol"
