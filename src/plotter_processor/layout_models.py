from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RectMM:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


@dataclass(frozen=True, slots=True)
class PageTransform:
    source_page_width_mm: float
    source_page_height_mm: float
    source_content_rect: RectMM
    target_content_rect: RectMM
    scale: float
    offset_x_mm: float
    offset_y_mm: float

    @classmethod
    def create(
        cls,
        source_page_width_mm: float,
        source_page_height_mm: float,
        target_content_rect: RectMM,
        *,
        source_content_rect: RectMM | None = None,
        max_upscale: float = 1.10,
    ) -> PageTransform:
        if source_page_width_mm <= 0 or source_page_height_mm <= 0:
            raise ValueError("Source page dimensions must be positive")
        source_content = source_content_rect or RectMM(
            0.0, 0.0, source_page_width_mm, source_page_height_mm
        )
        if source_content.width <= 0 or source_content.height <= 0:
            raise ValueError("Source content rectangle must be positive")
        scale = min(
            target_content_rect.width / source_content.width,
            target_content_rect.height / source_content.height,
            max_upscale,
        )
        mapped_width = source_content.width * scale
        mapped_height = source_content.height * scale
        offset_x = (
            target_content_rect.x
            + (target_content_rect.width - mapped_width) / 2
            - source_content.x * scale
        )
        offset_y = (
            target_content_rect.y
            + (target_content_rect.height - mapped_height) / 2
            - source_content.y * scale
        )
        return cls(
            source_page_width_mm,
            source_page_height_mm,
            source_content,
            target_content_rect,
            scale,
            offset_x,
            offset_y,
        )

    def map_point(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        return (
            self.offset_x_mm + x_mm * self.scale,
            self.offset_y_mm + y_mm * self.scale,
        )

    def map_rect(self, rect: RectMM) -> RectMM:
        x, y = self.map_point(rect.x, rect.y)
        return RectMM(x, y, self.scale_length(rect.width), self.scale_length(rect.height))

    def scale_length(self, value_mm: float) -> float:
        return value_mm * self.scale

    def map_relative_x(self, fraction: float) -> float:
        return self.target_content_rect.x + self.target_content_rect.width * fraction

    def map_relative_y(self, fraction: float) -> float:
        return self.target_content_rect.y + self.target_content_rect.height * fraction

    def payload(self) -> dict[str, object]:
        return {
            "source_width_mm": round(self.source_page_width_mm, 6),
            "source_height_mm": round(self.source_page_height_mm, 6),
            "source_content_rect": rect_payload(self.source_content_rect),
            "target_content_rect": rect_payload(self.target_content_rect),
            "scale": round(self.scale, 6),
            "offset_x_mm": round(self.offset_x_mm, 6),
            "offset_y_mm": round(self.offset_y_mm, 6),
        }


@dataclass(frozen=True, slots=True)
class SourcePlacement:
    source_page_index: int
    source_bbox: RectMM | None
    target_bbox: RectMM | None
    anchor: str
    wrap_mode: str
    z_order: int


@dataclass(frozen=True, slots=True)
class ExclusionZone:
    bbox: RectMM
    wrap_side: str
    element_id: str
    padding_left_mm: float = 0.0
    padding_right_mm: float = 0.0
    padding_top_mm: float = 0.0
    padding_bottom_mm: float = 0.0

    @property
    def padded_bbox(self) -> RectMM:
        return RectMM(
            self.bbox.x - self.padding_left_mm,
            self.bbox.y - self.padding_top_mm,
            self.bbox.width + self.padding_left_mm + self.padding_right_mm,
            self.bbox.height + self.padding_top_mm + self.padding_bottom_mm,
        )


def map_source_rect(
    source_rect: RectMM,
    source_page_size: tuple[float, float],
    target_content_rect: RectMM,
    *,
    max_upscale: float = 1.10,
) -> RectMM:
    if source_rect.width < 0 or source_rect.height < 0:
        raise ValueError("Source rectangle dimensions cannot be negative")
    return PageTransform.create(
        *source_page_size,
        target_content_rect,
        max_upscale=max_upscale,
    ).map_rect(source_rect)


def available_intervals(
    left: float,
    right: float,
    y_top: float,
    y_bottom: float,
    zones: list[ExclusionZone] | tuple[ExclusionZone, ...],
) -> list[tuple[float, float]]:
    intervals = [(left, right)]
    for zone in zones:
        box = zone.padded_bbox
        if y_bottom <= box.y or y_top >= box.bottom:
            continue
        if zone.wrap_side == "top_bottom":
            return []
        updated: list[tuple[float, float]] = []
        for start, end in intervals:
            if box.right <= start or box.x >= end:
                updated.append((start, end))
                continue
            if zone.wrap_side in {"both", "right"} and start < box.x:
                updated.append((start, min(end, box.x)))
            if zone.wrap_side in {"both", "left"} and box.right < end:
                updated.append((max(start, box.right), end))
        intervals = [(start, end) for start, end in updated if end - start > 0]
    return sorted(intervals)


def choose_widest_interval(intervals: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not intervals:
        return None
    return max(intervals, key=lambda value: (value[1] - value[0], -value[0]))


def intersection_area(first: RectMM, second: RectMM) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.y, second.y))
    return width * height


def center_displacement(first: RectMM, second: RectMM) -> float:
    return math.dist(first.center, second.center)


def rect_payload(rect: RectMM | None) -> dict[str, float] | None:
    if rect is None:
        return None
    return {
        "x": round(rect.x, 6),
        "y": round(rect.y, 6),
        "width": round(rect.width, 6),
        "height": round(rect.height, 6),
    }
