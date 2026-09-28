from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import isfinite

from plotter_processor.fast_word import WordBuilder, WordGeometry
from plotter_processor.models import PathDocument, PlotterStroke, Point

_TOKENS = re.compile(r"\f|\n|[^\S\n\f]+|[^\s\f]+")


@dataclass(frozen=True, slots=True)
class FastLayoutConfig:
    page_width_mm: float = 148.0
    page_height_mm: float = 210.0
    margin_left_mm: float = 2.0
    margin_right_mm: float = 2.0
    margin_top_mm: float = 2.0
    margin_bottom_mm: float = 2.0
    font_size_mm: float = 4.0
    line_height_mm: float | None = None
    word_spacing_mm: float | None = None
    line_gap_mm: float = 0.5

    def __post_init__(self) -> None:
        values = {
            "page_width_mm": self.page_width_mm,
            "page_height_mm": self.page_height_mm,
            "margin_left_mm": self.margin_left_mm,
            "margin_right_mm": self.margin_right_mm,
            "margin_top_mm": self.margin_top_mm,
            "margin_bottom_mm": self.margin_bottom_mm,
            "font_size_mm": self.font_size_mm,
        }
        if self.line_height_mm is not None:
            values["line_height_mm"] = self.line_height_mm
        if self.word_spacing_mm is not None:
            values["word_spacing_mm"] = self.word_spacing_mm
        for name, value in values.items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite value greater than zero")
        if not isfinite(self.line_gap_mm) or self.line_gap_mm < 0:
            raise ValueError("line_gap_mm must be a finite non-negative value")
        if self.content_width_mm <= 0 or self.content_height_mm <= 0:
            raise ValueError("page margins must leave a positive content area")
        if self.content_height_mm < self.font_size_mm:
            raise ValueError("page content height must fit at least one line of the selected font size")

    @property
    def content_width_mm(self) -> float:
        return self.page_width_mm - self.margin_left_mm - self.margin_right_mm

    @property
    def content_height_mm(self) -> float:
        return self.page_height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def resolved_line_height_mm(self) -> float:
        return self.line_height_mm if self.line_height_mm is not None else self.font_size_mm * 1.1

    @property
    def resolved_word_spacing_mm(self) -> float:
        return self.word_spacing_mm if self.word_spacing_mm is not None else self.font_size_mm * 0.2


@dataclass(slots=True)
class FastLayoutResult:
    pages: list[PathDocument]
    words_total: int
    pen_down_count: int
    cache_hits: int
    cache_misses: int
    missing_chars: set[str] = field(default_factory=set)

    @property
    def avg_pen_down_per_word(self) -> float:
        return self.pen_down_count / self.words_total if self.words_total else 0.0


class FastLayout:
    """Single-pass words -> lines -> pages layout for plain text."""

    def __init__(self, config: FastLayoutConfig) -> None:
        self.config = config

    def layout(self, text: str, builder: WordBuilder) -> FastLayoutResult:
        cfg = self.config
        scale = cfg.font_size_mm / builder.font.units_per_em
        word_spacing = cfg.resolved_word_spacing_mm
        right = cfg.page_width_mm - cfg.margin_right_mm
        bottom = cfg.page_height_mm - cfg.margin_bottom_mm
        ascent = max(builder.font.compiled.ascent * scale, 0.0)
        descent = max(-builder.font.compiled.descent * scale, 0.0)
        line_height = max(
            cfg.resolved_line_height_mm,
            ascent + descent + cfg.line_gap_mm,
        )
        pages: list[list[PlotterStroke]] = [[]]
        x = cfg.margin_left_mm
        baseline = cfg.margin_top_mm + ascent
        line_has_word = False
        words_total = 0
        missing: set[str] = set()

        def new_page() -> None:
            nonlocal x, baseline, line_has_word
            pages.append([])
            x = cfg.margin_left_mm
            baseline = cfg.margin_top_mm + ascent
            line_has_word = False

        def new_line() -> None:
            nonlocal x, baseline, line_has_word
            x = cfg.margin_left_mm
            baseline += line_height
            line_has_word = False
            if baseline + descent > bottom:
                new_page()

        for token in _TOKENS.findall(text.replace("\r\n", "\n").replace("\r", "\n")):
            if token == "\f":
                if pages[-1]:
                    new_page()
                continue
            if token == "\n":
                new_line()
                continue
            if token.isspace():
                if line_has_word:
                    x += word_spacing
                continue
            geometry = builder.build(token)
            word_scale = min(
                scale,
                (right - cfg.margin_left_mm) / geometry.advance_font_units
                if geometry.advance_font_units > 0
                else scale,
            )
            width = geometry.advance_font_units * word_scale
            if line_has_word and x + width > right:
                new_line()
            pages[-1].extend(_place_word(geometry, x, baseline, word_scale, words_total))
            missing.update(geometry.missing)
            words_total += 1
            x += width
            line_has_word = True

        documents = [
            PathDocument(
                cfg.page_width_mm,
                cfg.page_height_mm,
                strokes,
                [],
                {"pipeline": "fast-text", "page_index": index},
            )
            for index, strokes in enumerate(pages)
            if strokes or index == 0
        ]
        pen_down = sum(len(page.strokes) for page in documents)
        return FastLayoutResult(
            documents,
            words_total,
            pen_down,
            builder.cache_hits,
            builder.cache_misses,
            missing,
        )


def _place_word(
    geometry: WordGeometry,
    x: float,
    baseline: float,
    scale: float,
    word_index: int,
) -> list[PlotterStroke]:
    result: list[PlotterStroke] = []
    for source in geometry.strokes:
        points = [Point(x + point.x * scale, baseline - point.y * scale) for point in source.points]
        if len(points) < 2:
            continue
        result.append(
            PlotterStroke(
                id=len(result),
                points=points,
                closed=source.closed,
                source_chars=geometry.text,
                word_index=word_index,
                preserve_order=True,
            )
        )
    return result
