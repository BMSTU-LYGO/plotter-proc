from __future__ import annotations

import json
from pathlib import Path

from plotter_processor.models import PageSpec, PlotterStroke
from plotter_processor.semantic_metrics import semantic_report


def export_semantic_debug(output: Path, page: PageSpec, strokes: list[PlotterStroke]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    roles: dict[str, int] = {}
    for stroke in strokes:
        role = stroke.semantic_role or "generic"
        roles[role] = roles.get(role, 0) + 1
    (output / "classification.json").write_text(
        json.dumps({**semantic_report(strokes), "roles": roles}, indent=2) + "\n",
        encoding="utf-8",
    )
    subsets = {
        "primitives.svg": strokes,
        "classification.svg": strokes,
        "tables.svg": [stroke for stroke in strokes if stroke.semantic_role == "table-border"],
        "arrows.svg": [stroke for stroke in strokes if (stroke.semantic_role or "").startswith("arrow")],
        "underlines.svg": [stroke for stroke in strokes if stroke.semantic_role == "underline"],
    }
    for name, selected in subsets.items():
        _svg(output / name, page, selected)


def _svg(path: Path, page: PageSpec, strokes: list[PlotterStroke]) -> None:
    colors = {"underline": "#d32f2f", "table-border": "#1976d2", "arrow-shaft": "#388e3c", "arrow-head-start": "#388e3c", "arrow-head-end": "#388e3c"}
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {page.width_mm} {page.height_mm}">']
    for stroke in strokes:
        points = " ".join(f"{point.x:.4f},{point.y:.4f}" for point in stroke.points)
        role = stroke.semantic_role or "generic"
        lines.append(f'<polyline points="{points}" fill="none" stroke="{colors.get(role, "#555")}" stroke-width="0.3" data-semantic-role="{role}"/>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
