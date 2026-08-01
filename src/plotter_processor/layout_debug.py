from __future__ import annotations

import json
from pathlib import Path

from plotter_processor.layout_models import RectMM
from plotter_processor.models import PageSpec


def export_layout_debug(
    output_dir: Path,
    page: PageSpec,
    placements: list[dict[str, object]],
    line_boxes: list[dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"coordinate_unit": "mm", "elements": placements, "text_line_boxes": line_boxes}
    (output_dir / "placement.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_svg(output_dir / "source-layout.svg", page, placements, [], "source")
    _write_svg(output_dir / "target-layout.svg", page, placements, line_boxes, "output")
    _write_svg(output_dir / "placement-overlay.svg", page, placements, line_boxes, "overlay")


def _write_svg(
    path: Path,
    page: PageSpec,
    placements: list[dict[str, object]],
    line_boxes: list[dict[str, object]],
    mode: str,
) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {page.width_mm} {page.height_mm}">',
        (
            f'<rect x="0" y="0" width="{page.width_mm}" height="{page.height_mm}" '
            'fill="white" stroke="#222" stroke-width="0.25"/>'
        ),
    ]
    if mode in {"output", "overlay"}:
        for item in line_boxes:
            rect = _rect(item.get("bbox"))
            if rect is not None:
                lines.append(_rect_svg(rect, "#3a7", "0.10", "none", "2 1"))
    for item in placements:
        source = _rect(item.get("mapped_bbox_mm"))
        output = _rect(item.get("output_bbox_mm"))
        if mode in {"source", "overlay"} and source is not None:
            lines.append(_rect_svg(source, "#777", "0.25", "none", "2 1"))
        if mode in {"output", "overlay"} and output is not None:
            lines.append(_rect_svg(output, "#1565c0", "0.35", "#1565c018", None))
        if mode == "overlay" and source is not None and output is not None:
            sx, sy = source.center
            ox, oy = output.center
            lines.append(
                f'<line x1="{sx:.4f}" y1="{sy:.4f}" x2="{ox:.4f}" y2="{oy:.4f}" '
                'stroke="#d32f2f" stroke-width="0.3"/>'
            )
        label_rect = output or source
        if label_rect is not None:
            lines.append(
                f'<text x="{label_rect.x:.4f}" y="{max(2.5, label_rect.y - 0.8):.4f}" '
                f'font-size="2.2" fill="#222">{_escape(str(item.get("id", "")))}</text>'
            )
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rect(value: object) -> RectMM | None:
    if not isinstance(value, dict):
        return None
    try:
        return RectMM(
            float(value["x"]),
            float(value["y"]),
            float(value["width"]),
            float(value["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _rect_svg(
    rect: RectMM, stroke: str, width: str, fill: str, dash: str | None
) -> str:
    dash_value = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{rect.x:.4f}" y="{rect.y:.4f}" width="{rect.width:.4f}" '
        f'height="{rect.height:.4f}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{width}"{dash_value}/>'
    )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
