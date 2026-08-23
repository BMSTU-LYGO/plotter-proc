from __future__ import annotations

import math
from collections.abc import Mapping

from plotter_processor.document_models import (
    SourceRasterImageElement,
    SourceVectorElement,
)
from plotter_processor.layout_models import (
    RectMM,
    center_displacement,
    intersection_area,
    rect_payload,
)
from plotter_processor.models import Point


def rotated_size(width: float, height: float, rotation_deg: float) -> tuple[float, float]:
    angle = math.radians(rotation_deg % 360)
    cosine = abs(math.cos(angle))
    sine = abs(math.sin(angle))
    return width * cosine + height * sine, width * sine + height * cosine


def rotate_image_point(
    point: Point,
    target_bbox: RectMM,
    width: float,
    height: float,
    rotation_deg: float,
) -> Point:
    if abs(rotation_deg % 360) < 1e-9:
        return Point(target_bbox.x + point.x, target_bbox.y + point.y)
    angle = math.radians(rotation_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    local_x, local_y = point.x - width / 2, point.y - height / 2
    rotated_x = local_x * cosine - local_y * sine
    rotated_y = local_x * sine + local_y * cosine
    return Point(
        target_bbox.x + target_bbox.width / 2 + rotated_x,
        target_bbox.y + target_bbox.height / 2 + rotated_y,
    )


def scaled_padding(
    value: float,
    page_scale: float,
    image_options: Mapping[str, object],
) -> float:
    if value <= 0:
        return 0.0
    scaled = value * page_scale
    return min(
        float(image_options.get("max_wrap_padding_mm", 8.0)),
        max(float(image_options.get("min_wrap_padding_mm", 0.7)), scaled),
    )


def place_raster(
    element: SourceRasterImageElement,
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
) -> tuple[RectMM, str, list[str]]:
    inline = element.wrap_mode == "inline" or element.anchor_type == "flow"
    return _place_graphic(
        mode,
        mapped,
        width,
        height,
        cursor_y,
        content,
        previous,
        options,
        spacing_before,
        element.wrap_mode,
        inline=inline,
        source_position_available=element.bbox is not None,
        relative_to_v=element.relative_to_v,
    )


def place_vector(
    element: SourceVectorElement,
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
) -> tuple[RectMM, str, list[str]]:
    return _place_graphic(
        mode,
        mapped,
        width,
        height,
        cursor_y,
        content,
        previous,
        options,
        spacing_before,
        element.wrap_mode,
        inline=False,
        source_position_available=element.bbox is not None,
        relative_to_v="page",
    )


def _place_graphic(
    mode: str,
    mapped: RectMM | None,
    width: float,
    height: float,
    cursor_y: float,
    content: RectMM,
    previous: list[dict[str, object]],
    options: Mapping[str, object],
    spacing_before: float,
    wrap_mode: str,
    *,
    inline: bool,
    source_position_available: bool,
    relative_to_v: str | None,
) -> tuple[RectMM, str, list[str]]:
    warnings: list[str] = []
    if mode == "reflow" or inline:
        return (
            RectMM(
                content.x + (content.width - width) / 2,
                cursor_y + spacing_before,
                width,
                height,
            ),
            "inline" if inline else "top_bottom",
            warnings,
        )
    if mapped is None:
        warnings.append("image_source_position_unavailable")
        rect = RectMM(content.x, cursor_y + spacing_before, width, height)
    elif mode == "preserve":
        rect = mapped
    else:
        x = min(max(mapped.x, content.x), content.right - width)
        y = mapped.y if relative_to_v in {"page", "margin"} else cursor_y + spacing_before
        y = min(max(y, content.y), content.bottom - height)
        rect = RectMM(x, y, width, height)
    effective_wrap = wrap_mode
    if mode == "hybrid" and effective_wrap == "none":
        effective_wrap = "square"
        warnings.append("image_wrap_none_approximated_as_square")
    if mode == "hybrid":
        max_shift = float(options.get("max_vertical_shift_mm", 25.0))
        attempts = max(1, int(options.get("max_placement_attempts", 20)))
        initial_y = rect.y
        for _attempt in range(attempts):
            conflicts = [
                existing
                for item in previous
                if (existing := payload_rect(item.get("output_bbox_mm"))) is not None
                and intersection_area(rect, existing) > 1e-9
            ]
            if not conflicts:
                break
            next_y = max(conflict.bottom for conflict in conflicts) + float(
                options.get("image_padding_mm", 2.0)
            )
            if next_y - initial_y > max_shift or next_y + rect.height > content.bottom:
                effective_wrap = "top_bottom"
                warnings.append("image_wrap_fallback_top_bottom")
                rect = RectMM(
                    rect.x,
                    max(cursor_y + spacing_before, initial_y),
                    rect.width,
                    rect.height,
                )
                break
            rect = RectMM(rect.x, next_y, rect.width, rect.height)
            warnings.append("image_overlap_avoided")
    clamped = RectMM(
        min(max(rect.x, content.x), content.right - rect.width),
        min(max(rect.y, content.y), content.bottom - rect.height),
        min(rect.width, content.width),
        min(rect.height, content.height),
    )
    if center_displacement(rect, clamped) > 1e-6:
        warnings.append("image_position_shifted")
    if not source_position_available and "image_source_position_unavailable" not in warnings:
        warnings.append("image_source_position_unavailable")
    return clamped, effective_wrap, list(dict.fromkeys(warnings))


def placement_record(
    element_id: str,
    source_order: int,
    source_page_index: int,
    target_page_index: int,
    source_bbox: object,
    mapped: RectMM | None,
    output: RectMM,
    anchor: str,
    wrap_mode: str,
    wrap_side: str,
    original_width: float | None,
    warnings: list[str],
    element_type: str,
    placement_reason: str,
) -> dict[str, object]:
    source_rect = (
        RectMM(source_bbox.x0, source_bbox.y0, source_bbox.width, source_bbox.height)
        if source_bbox is not None
        else None
    )
    displacement = center_displacement(mapped, output) if mapped is not None else None
    scale = output.width / original_width if original_width and original_width > 0 else 1.0
    return {
        "id": element_id,
        "element_type": element_type,
        "source_order": source_order,
        "source_page_index": source_page_index,
        "source_bbox_mm": rect_payload(source_rect),
        "mapped_bbox_mm": rect_payload(mapped),
        "output_bbox_mm": rect_payload(output),
        "target_page_index": target_page_index,
        "anchor": anchor,
        "wrap_mode": wrap_mode,
        "wrap_side": wrap_side,
        "scale": round(scale, 6),
        "center_displacement_mm": round(displacement, 6) if displacement is not None else None,
        "overlap_area_mm2": 0.0,
        "page_overflow_area_mm2": 0.0,
        "fallbacks": list(dict.fromkeys(warnings)),
        "placement_reason": placement_reason,
    }


def payload_rect(value: object) -> RectMM | None:
    if not isinstance(value, Mapping):
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
