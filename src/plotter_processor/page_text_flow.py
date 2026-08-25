from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import lru_cache

from plotter_processor.font_loader import LoadedFont
from plotter_processor.layout_models import (
    ExclusionZone,
    RectMM,
    available_intervals,
    choose_widest_interval,
)
from plotter_processor.models import PageSpec
from plotter_processor.page_layout_model import PageLayoutState
from plotter_processor.vector_layout import layout_text


@lru_cache(maxsize=8192)
def text_width(text: str, font: LoadedFont, scale: float) -> float:
    return sum(
        font.advance_for_glyph(font.glyph_name_for_char(character)) * scale
        for character in text
    )


def zone_payloads(zones: list[ExclusionZone]) -> list[dict[str, object]]:
    from plotter_processor.layout_models import rect_payload

    return [
        {
            "element_id": zone.element_id,
            "bbox": rect_payload(zone.padded_bbox),
            "wrap_side": zone.wrap_side,
        }
        for zone in zones
    ]


def clear_blocking_zones(
    cursor_y: float,
    height: float,
    zones: list[ExclusionZone],
) -> float:
    current = cursor_y
    while True:
        blockers = [
            zone.padded_bbox
            for zone in zones
            if not (
                current + height <= zone.padded_bbox.y
                or current >= zone.padded_bbox.bottom
            )
        ]
        if not blockers:
            return current
        current = max(box.bottom for box in blockers)


def prune_expired_zones(zones: list[ExclusionZone], cursor_y: float) -> None:
    zones[:] = [zone for zone in zones if zone.padded_bbox.bottom > cursor_y + 1e-9]


def layout_text_around_zones(
    paragraph: str,
    state: PageLayoutState,
    font: LoadedFont,
    page: PageSpec,
    margins: Mapping[str, object],
    size_options: Mapping[str, object],
    content_bottom: float,
    glyph_height: float,
    line_advance: float,
    scale: float,
    add_source_id: Callable[[str], None],
    element_id: str,
    finish_page: Callable[[], PageLayoutState],
    *,
    tab_spaces: int,
    engine: str,
    language: str,
    script: str,
    direction: str,
    features: tuple[str, ...],
) -> None:
    remaining = paragraph.strip()
    left = _number(margins, "left")
    right = page.width_mm - _number(margins, "right")
    while remaining:
        if state.cursor_y + glyph_height > content_bottom + 1e-9:
            state = finish_page()
        prune_expired_zones(state.exclusion_zones, state.cursor_y)
        intervals = available_intervals(
            left,
            right,
            state.cursor_y,
            state.cursor_y + line_advance,
            state.exclusion_zones,
        )
        interval = choose_widest_interval(intervals)
        if interval is None:
            state.cursor_y = clear_blocking_zones(
                state.cursor_y, line_advance, state.exclusion_zones
            )
            continue
        line, remaining = take_text_line(
            remaining, interval[1] - interval[0], font, scale
        )
        local_margins = dict(margins)
        local_margins.update(
            {
                "left": interval[0],
                "right": page.width_mm - interval[1],
                "top": 0.0,
                "bottom": 0.0,
            }
        )
        flowed = layout_text(
            [line],
            font,
            PageSpec("flow-line", page.width_mm, 1_000_000.0),
            local_margins,
            size_options,
            tab_spaces=tab_spaces,
            engine=engine,
            language=language,
            script=script,
            direction=direction,
            features=features,
        )
        baseline = state.cursor_y + font.metrics.ascent * scale
        global_line = state.line_count
        for glyph in flowed.glyphs:
            state.glyphs.append(
                replace(
                    glyph,
                    baseline_y_mm=baseline,
                    line_index=global_line,
                    glyph_index=len(state.glyphs),
                )
            )
        used_width = sum(glyph.advance_mm for glyph in flowed.glyphs)
        state.line_boxes.append(
            RectMM(
                interval[0],
                state.cursor_y,
                min(used_width, interval[1] - interval[0]),
                line_advance,
            )
        )
        state.cursor_y += line_advance
        state.line_count += 1
        add_source_id(element_id)


def take_text_line(
    text: str, max_width: float, font: LoadedFont, scale: float
) -> tuple[str, str]:
    words = text.split()
    if not words:
        return "", ""
    current = words[0]
    if text_width(current, font, scale) > max_width:
        split = 1
        while (
            split < len(current)
            and text_width(current[: split + 1], font, scale) <= max_width
        ):
            split += 1
        return current[:split], " ".join([current[split:], *words[1:]]).strip()
    consumed = 1
    while consumed < len(words):
        candidate = f"{current} {words[consumed]}"
        if text_width(candidate, font, scale) > max_width:
            break
        current = candidate
        consumed += 1
    return current, " ".join(words[consumed:])


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid non-negative field: {key}")
    return float(value)
