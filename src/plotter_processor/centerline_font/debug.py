from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

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
    candidate_skeletons: dict[str, np.ndarray] | None = None,
) -> None:
    target = directory / f"U+{raster.codepoint:04X}-{_safe(raster.char)}"
    target.mkdir(parents=True, exist_ok=True)
    Image.fromarray(raster.grayscale).save(target / "00_raster.png")
    _save_binary(mask, target / "01_mask.png")
    maximum = max(1.0, float(distance.max()))
    Image.fromarray(np.asarray(distance / maximum * 255, dtype=np.uint8)).save(
        target / "02_distance.png"
    )
    for method, candidate in sorted((candidate_skeletons or {}).items()):
        number = "03" if method == "skeletonize" else "04"
        _save_binary(candidate, target / f"{number}_skeleton_{method}.png")
    _save_binary(pruned, target / "05_selected_skeleton.png")
    (target / "06_graph_nodes_edges.svg").write_text(
        _graph_svg(raster.width, raster.height, nodes, edges), encoding="utf-8"
    )
    stroke_svg = _stroke_svg(raster, strokes)
    (target / "07_routes.svg").write_text(stroke_svg, encoding="utf-8")
    (target / "08_smoothed_strokes.svg").write_text(stroke_svg, encoding="utf-8")
    radii = distance[pruned]
    radius = max(1, round(float(np.median(radii)))) if radii.size else 1
    reconstructed = ndimage.binary_dilation(pruned, iterations=radius)
    _save_binary(reconstructed, target / "09_reconstructed_mask.png")
    difference = np.zeros((*mask.shape, 3), dtype=np.uint8)
    difference[:] = (255, 255, 255)
    difference[mask & ~reconstructed] = (220, 30, 30)
    difference[reconstructed & ~mask] = (30, 90, 220)
    Image.fromarray(difference).save(target / "10_mask_difference.png")
    (target / "11_overlay.svg").write_text(
        _overlay_svg(raster, mask, nodes, edges, strokes), encoding="utf-8"
    )
    (target / "metrics.json").write_text(
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


def _overlay_svg(
    raster: RasterGlyph,
    mask: np.ndarray,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    strokes: list[CenterlineStroke],
) -> str:
    boundary = mask & ~ndimage.binary_erosion(mask)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {raster.width} {raster.height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g id="mask-boundary" fill="#777" opacity="0.3">',
    ]
    for y, x in np.argwhere(boundary):
        lines.append(f'<rect x="{x}" y="{y}" width="1" height="1"/>')
    lines.append('</g><g id="centerline" fill="none" stroke="#1565c0" stroke-width="1.5">')
    for stroke in strokes:
        points = " ".join(
            f"{raster.baseline_x_px + p.x * raster.pixels_per_font_unit},"
            f"{raster.baseline_y_px - p.y * raster.pixels_per_font_unit}"
            for p in stroke.points
        )
        lines.append(f'<polyline points="{points}"/>')
    lines.append('</g><g id="graph-labels" font-size="8">')
    colors = {"endpoint": "#2e7d32", "junction": "#c62828"}
    for node in nodes:
        color = colors.get(node.kind, "#6a1b9a")
        lines.append(f'<circle cx="{node.x}" cy="{node.y}" r="3" fill="{color}"/>')
        lines.append(
            f'<text x="{node.x + 4}" y="{node.y - 4}" fill="{color}">'
            f"n{node.id}/c{node.component_id}</text>"
        )
    for edge in edges:
        if not edge.pixels:
            continue
        y, x = edge.pixels[len(edge.pixels) // 2]
        lines.append(f'<text x="{x + 2}" y="{y + 2}" fill="#222">e{edge.id}</text>')
    lines.append("</g></svg>")
    return "\n".join(lines) + "\n"


def _safe(char: str) -> str:
    return char if char.isalnum() else "symbol"
