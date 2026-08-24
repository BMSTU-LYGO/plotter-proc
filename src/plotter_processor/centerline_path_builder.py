from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field

from plotter_processor.centerline_font.models import (
    CenterlineGlyph,
    CompiledPlotterFont,
)
from plotter_processor.models import PageSpec, PathDocument, PlotterStroke, Point, PositionedGlyph
from plotter_processor.performance import HotspotTimings


@dataclass(frozen=True, slots=True)
class _LocalStrokeTemplate:
    id: int
    points: tuple[Point, ...]
    closed: bool


@dataclass(slots=True)
class CenterlinePathTemplateCache:
    """Ephemeral per-run cache of scaled glyph geometry before translation."""

    entries: dict[
        tuple[str, str, float], tuple[_LocalStrokeTemplate, ...]
    ] = field(default_factory=dict)
    positioned_entries: dict[
        tuple[str, str, float, float, float], tuple[tuple[Point, ...], ...]
    ] = field(default_factory=dict)
    template_cache_hits: int = 0
    template_cache_misses: int = 0
    local_points_built: int = 0
    output_points_allocated: int = 0
    positioned_template_hits: int = 0
    positioned_template_misses: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "build_template_cache_hits": self.template_cache_hits,
            "build_template_cache_misses": self.template_cache_misses,
            "build_local_points_built": self.local_points_built,
            "build_output_points_allocated": self.output_points_allocated,
            "build_positioned_template_hits": self.positioned_template_hits,
            "build_positioned_template_misses": self.positioned_template_misses,
        }


def build_centerline_paths(
    compiled_font: CompiledPlotterFont,
    glyphs: list[PositionedGlyph],
    page: PageSpec,
    *,
    template_cache: CenterlinePathTemplateCache | None = None,
    hotspots: HotspotTimings | None = None,
) -> PathDocument:
    cache = template_cache or CenterlinePathTemplateCache()
    strokes: list[PlotterStroke] = []
    for positioned in glyphs:
        try:
            glyph = compiled_font.glyphs[positioned.char]
        except KeyError as error:
            raise ValueError(
                f'Centerline cache is missing glyph "{positioned.char}" '
                f"(U+{positioned.codepoint:04X})"
            ) from error
        with hotspots.measure("build_paths.template_lookup") if hotspots else nullcontext():
            templates = _local_templates(compiled_font, glyph, positioned, cache)
        with hotspots.measure("build_paths.transform") if hotspots else nullcontext():
            positioned_points = _positioned_points(
                compiled_font, positioned, templates, cache
            )
        with hotspots.measure("build_paths.stroke_materialization") if hotspots else nullcontext():
            for template, cached_points in zip(templates, positioned_points, strict=True):
                points = list(cached_points)
                strokes.append(
                    PlotterStroke(
                        id=len(strokes),
                        points=points,
                        closed=template.closed,
                        glyph_index=positioned.glyph_index,
                        char=positioned.char,
                        contour_index=template.id,
                        source_glyph_indices=(positioned.glyph_index,),
                        source_chars=positioned.char,
                        segment_types=("glyph",),
                        word_index=positioned.word_index,
                    )
                )
    if not strokes:
        raise ValueError("Font processing produced no drawable paths")
    return PathDocument(
        page.width_mm,
        page.height_mm,
        strokes,
        list(compiled_font.warnings),
        {
            "coordinate_system": "page-mm-top-left",
            "pipeline": "ttf-centerline",
            "centerline_format": "plotter-centerline-font",
            "centerline_version": compiled_font.schema_version,
            "routing_strategy": "one_stroke_per_component",
            "font_sha256": compiled_font.font_sha256,
        },
    )


def _local_templates(
    compiled_font: CompiledPlotterFont,
    glyph: CenterlineGlyph,
    positioned: PositionedGlyph,
    cache: CenterlinePathTemplateCache,
) -> tuple[_LocalStrokeTemplate, ...]:
    key = (
        compiled_font.font_sha256,
        positioned.char,
        positioned.scale_mm_per_font_unit,
    )
    cached = cache.entries.get(key)
    if cached is not None:
        cache.template_cache_hits += 1
        return cached
    cache.template_cache_misses += 1
    templates: list[_LocalStrokeTemplate] = []
    metadata_by_stroke = {item.stroke_id: item for item in glyph.stroke_metadata}
    ordered_strokes = sorted(
        enumerate(glyph.strokes),
        key=lambda item: (
            metadata_by_stroke.get(item[1].id).recommended_order
            if metadata_by_stroke.get(item[1].id) is not None
            and metadata_by_stroke[item[1].id].recommended_order is not None
            else item[0]
        ),
    )
    for _, centerline in ordered_strokes:
        points = _dedupe(
            [
                Point(
                    point.x * positioned.scale_mm_per_font_unit,
                    -point.y * positioned.scale_mm_per_font_unit,
                )
                for point in centerline.points
            ]
        )
        cache.local_points_built += len(points)
        if len(points) < (3 if centerline.closed else 2):
            continue
        metadata = metadata_by_stroke.get(centerline.id)
        if metadata is not None and metadata.recommended_direction == "reverse":
            points.reverse()
        templates.append(
            _LocalStrokeTemplate(centerline.id, tuple(points), centerline.closed)
        )
    result = tuple(templates)
    cache.entries[key] = result
    return result


def _positioned_points(
    compiled_font: CompiledPlotterFont,
    positioned: PositionedGlyph,
    templates: tuple[_LocalStrokeTemplate, ...],
    cache: CenterlinePathTemplateCache,
) -> tuple[tuple[Point, ...], ...]:
    key = (
        compiled_font.font_sha256,
        positioned.char,
        positioned.scale_mm_per_font_unit,
        positioned.x_mm,
        positioned.baseline_y_mm,
    )
    cached = cache.positioned_entries.get(key)
    if cached is not None:
        cache.positioned_template_hits += 1
        return cached
    cache.positioned_template_misses += 1
    result = tuple(
        tuple(
            Point(
                positioned.x_mm + point.x,
                positioned.baseline_y_mm + point.y,
            )
            for point in template.points
        )
        for template in templates
    )
    cache.output_points_allocated += sum(len(points) for points in result)
    cache.positioned_entries[key] = result
    return result


def _dedupe(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return result
