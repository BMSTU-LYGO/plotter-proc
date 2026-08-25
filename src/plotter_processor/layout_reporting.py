from __future__ import annotations

from itertools import pairwise

from plotter_processor.graphic_placement import payload_rect
from plotter_processor.layout_models import RectMM, intersection_area


def build_layout_statistics(
    mode: str,
    placements: list[dict[str, object]],
    line_boxes: list[dict[str, object]],
    trace_records: list[dict[str, object]],
    line_advance: float,
) -> dict[str, object]:
    """Build placement diagnostics without participating in pagination."""
    graphics = [
        item
        for item in placements
        if item.get("element_type") in {"raster-image", "pdf-vector"}
    ]
    displacements = [
        float(value)
        for item in graphics
        if (value := item.get("center_displacement_mm")) is not None
    ]
    scales = [float(item.get("scale", 1.0)) for item in graphics]
    overlaps = 0.0
    for item in graphics:
        image = payload_rect(item.get("output_bbox_mm"))
        if image is None:
            continue
        for line in line_boxes:
            if int(line.get("page_index", -1)) != int(
                item.get("target_page_index", -2)
            ):
                continue
            text = payload_rect(line.get("bbox"))
            if text is not None:
                overlaps += intersection_area(image, text)
    threshold = 1.0 if mode == "preserve" else 10.0
    unexplained_gaps: list[float] = []
    lines_by_page: dict[int, list[RectMM]] = {}
    for item in line_boxes:
        rect = payload_rect(item.get("bbox"))
        if rect is not None:
            lines_by_page.setdefault(int(item.get("page_index", -1)), []).append(rect)
    for page_index, page_lines in lines_by_page.items():
        ordered = sorted(page_lines, key=lambda rect: (rect.y, rect.x))
        for previous, following in pairwise(ordered):
            gap = following.y - previous.bottom
            if gap <= 2.5 * line_advance + 1e-9:
                continue
            gap_top = previous.bottom
            gap_bottom = following.y
            explained_by_graphic = any(
                int(item.get("target_page_index", -2)) == page_index
                and (rect := payload_rect(item.get("output_bbox_mm"))) is not None
                and rect.bottom > gap_top
                and rect.y < gap_bottom
                for item in placements
            )
            explained_by_flow_event = any(
                int(item.get("page_index", -2)) == page_index
                and str(item.get("placement_reason"))
                in {
                    "explicit_blank_paragraph",
                    "configured_block_spacing",
                    "latex_in_flow",
                    "activated_at_source_order",
                }
                and float(item.get("cursor_y_before", 0.0)) < gap_bottom
                and float(item.get("cursor_y_after", 0.0)) > gap_top
                for item in trace_records
            )
            if not explained_by_graphic and not explained_by_flow_event:
                unexplained_gaps.append(gap)
    return {
        "mode": mode,
        "images": len(graphics),
        "images_with_source_bbox": sum(
            item.get("source_bbox_mm") is not None for item in graphics
        ),
        "images_wrapped": sum(
            item.get("wrap_mode") == "square" for item in graphics
        ),
        "images_top_bottom": sum(
            item.get("wrap_mode") == "top_bottom" for item in graphics
        ),
        "position_preserved": sum(
            item.get("center_displacement_mm") is not None
            and float(item["center_displacement_mm"]) <= threshold
            for item in graphics
        ),
        "position_fallbacks": sum(bool(item.get("fallbacks")) for item in graphics),
        "mean_center_displacement_mm": (
            round(sum(displacements) / len(displacements), 6)
            if displacements
            else None
        ),
        "max_center_displacement_mm": (
            round(max(displacements), 6) if displacements else None
        ),
        "mean_scale_factor": (
            round(sum(scales) / len(scales), 6) if scales else None
        ),
        "overlaps_remaining": round(overlaps, 6),
        "page_overflow_area_mm2": round(
            sum(
                float(item.get("page_overflow_area_mm2", 0.0))
                for item in graphics
            ),
            6,
        ),
        "max_unexplained_vertical_gap_mm": (
            round(max(unexplained_gaps), 6) if unexplained_gaps else 0.0
        ),
        "unexplained_vertical_gap_count": len(unexplained_gaps),
        "elements": placements,
    }
