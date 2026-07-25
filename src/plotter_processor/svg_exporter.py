from pathlib import Path
from typing import Any

import svgwrite

from plotter_processor.models import PathDocument


def export_svg(
    document: PathDocument,
    output_path: str | Path,
    *,
    margins_mm: dict[str, Any],
    show_travel: bool = False,
) -> None:
    margins = {
        name: _nonnegative_float(margins_mm.get(name), f"{name} margin")
        for name in ("left", "right", "top", "bottom")
    }
    usable_width = document.page_width_mm - margins["left"] - margins["right"]
    usable_height = document.page_height_mm - margins["top"] - margins["bottom"]
    if usable_width <= 0 or usable_height <= 0:
        raise ValueError("Page margins leave no usable preview area")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    drawing = svgwrite.Drawing(
        filename=str(path),
        size=(f"{document.page_width_mm}mm", f"{document.page_height_mm}mm"),
        viewBox=f"0 0 {document.page_width_mm} {document.page_height_mm}",
        profile="full",
    )
    drawing.add(
        drawing.rect(
            insert=(0, 0),
            size=(document.page_width_mm, document.page_height_mm),
            fill="white",
        )
    )
    drawing.add(
        drawing.rect(
            insert=(margins["left"], margins["top"]),
            size=(usable_width, usable_height),
            fill="none",
            stroke="#999",
            stroke_width=0.15,
            stroke_dasharray="1,1",
        )
    )

    previous_end: tuple[float, float] | None = None
    for stroke in document.strokes:
        if len(stroke.points) < 2:
            continue
        start = (stroke.points[0].x, stroke.points[0].y)
        if show_travel and previous_end is not None:
            drawing.add(
                drawing.line(
                    start=previous_end,
                    end=start,
                    stroke="#c9c9c9",
                    stroke_width=0.12,
                    stroke_dasharray="0.8,0.8",
                )
            )
        drawing.add(
            drawing.polyline(
                points=[(point.x, point.y) for point in stroke.points],
                fill="none",
                stroke="black",
                stroke_width=0.25,
                stroke_linecap="round",
                stroke_linejoin="round",
            )
        )
        drawing.add(drawing.circle(center=start, r=0.35, fill="#d22", stroke="none"))
        previous_end = (stroke.points[-1].x, stroke.points[-1].y)

    drawing.save(pretty=True)


def _nonnegative_float(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be non-negative")
    return float(value)
