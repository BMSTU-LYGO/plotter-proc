"""Linear, cache-backed assembly of glyphs into word strokes."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import hypot

from plotter_processor.centerline_font.models import CenterlineGlyph, CenterlineStroke
from plotter_processor.fast_font import FastFont
from plotter_processor.models import Point


@dataclass(frozen=True, slots=True)
class WordGeometry:
    text: str
    advance_font_units: float
    primary: tuple[CenterlineStroke, ...]
    secondary: tuple[CenterlineStroke, ...]
    missing: tuple[str, ...] = ()

    @property
    def strokes(self) -> tuple[CenterlineStroke, ...]:
        return self.primary + self.secondary


class WordBuilder:
    """Build words in O(characters), retaining a small LRU of completed words."""

    def __init__(self, font: FastFont, *, cache_size: int = 256, connector_limit: float = 0.75) -> None:
        if cache_size < 1:
            raise ValueError("cache_size must be positive")
        if connector_limit <= 0:
            raise ValueError("connector_limit must be positive")
        self.font = font
        self.cache_size = cache_size
        self.connector_limit = connector_limit
        self._cache: OrderedDict[str, WordGeometry] = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0

    def build(self, text: str) -> WordGeometry:
        cached = self._cache.get(text)
        if cached is not None:
            self.cache_hits += 1
            self._cache.move_to_end(text)
            return cached
        self.cache_misses += 1

        primary_points: list[Point] = []
        primary_closed = False
        secondary: list[CenterlineStroke] = []
        advance = 0.0
        missing: list[str] = []
        next_id = 1

        for char in text:
            glyph = self.font.get(char)
            if glyph is None:
                missing.append(char)
                continue
            main = _main_stroke(glyph)
            translated = tuple(Point(point.x + advance, point.y) for point in main.points) if main else ()
            placed_as_secondary = False
            if translated:
                if primary_points:
                    if not primary_closed and not main.closed:
                        connector = _connector(
                            primary_points[-1], translated[0], glyph.advance_font_units, self.connector_limit
                        )
                        if connector is not None:
                            primary_points.extend(connector[1:])
                        else:
                            # A distant/unsafe join remains a second pen-down stroke.
                            secondary.append(CenterlineStroke(next_id, translated, main.closed, main.component_id))
                            next_id += 1
                            placed_as_secondary = True
                    else:
                        secondary.append(CenterlineStroke(next_id, translated, main.closed, main.component_id))
                        next_id += 1
                        placed_as_secondary = True
                if not primary_points:
                    primary_points.extend(translated)
                    primary_closed = main.closed
                elif not placed_as_secondary:
                    primary_points.extend(translated[1:] if primary_points[-1] == translated[0] else translated)
            for stroke in glyph.strokes:
                if main is not None and stroke.id == main.id:
                    continue
                points = tuple(Point(point.x + advance, point.y) for point in stroke.points)
                secondary.append(CenterlineStroke(next_id, points, stroke.closed, stroke.component_id))
                next_id += 1
            advance += glyph.advance_font_units

        primary = (
            (CenterlineStroke(0, tuple(primary_points), primary_closed),)
            if len(primary_points) >= 2
            else ()
        )
        result = WordGeometry(text, advance, primary, tuple(secondary), tuple(missing))
        self._cache[text] = result
        self._cache.move_to_end(text)
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return result

    def clear_cache(self) -> None:
        self._cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0


def _main_stroke(glyph: CenterlineGlyph) -> CenterlineStroke | None:
    if not glyph.strokes:
        return None
    anchor_id = glyph.entry_anchor.stroke_id if glyph.entry_anchor else None
    anchored = next((stroke for stroke in glyph.strokes if stroke.id == anchor_id), None)
    stroke = anchored or max(glyph.strokes, key=lambda item: len(item.points))
    # Compiled anchors supply the natural writing direction without any route
    # search. Only endpoint anchors are safe for a one-stroke join.
    entry = glyph.entry_anchor
    exit_anchor = glyph.exit_anchor
    reverse = bool(entry and entry.stroke_id == stroke.id and entry.point_index == len(stroke.points) - 1)
    if not reverse and exit_anchor and exit_anchor.stroke_id == stroke.id and exit_anchor.point_index == 0:
        reverse = True
    if not reverse:
        return stroke
    return CenterlineStroke(stroke.id, tuple(reversed(stroke.points)), stroke.closed, stroke.component_id, stroke.retraced_length_font_units)


def _connector(start: Point, end: Point, advance: float, limit: float) -> tuple[Point, ...] | None:
    """A tiny quadratic transition; refuse joins that would cross a glyph."""
    distance = hypot(end.x - start.x, end.y - start.y)
    if distance == 0:
        return (start, end)
    if distance > max(1.0, abs(advance) * limit):
        return None
    control = Point((start.x + end.x) / 2, start.y)
    return tuple(
        Point(
            (1 - t) ** 2 * start.x + 2 * (1 - t) * t * control.x + t**2 * end.x,
            (1 - t) ** 2 * start.y + 2 * (1 - t) * t * control.y + t**2 * end.y,
        )
        for t in (0.0, 1 / 3, 2 / 3, 1.0)
    )
