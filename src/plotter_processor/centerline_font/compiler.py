from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import default_cache_path, font_sha256
from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.debug import export_glyph_debug
from plotter_processor.centerline_font.edge_geometry import build_smoothed_edge_geometry
from plotter_processor.centerline_font.glyph_renderer import render_glyph
from plotter_processor.centerline_font.mask_processor import build_ink_mask
from plotter_processor.centerline_font.models import CenterlineGlyph, CompiledCenterlineFont
from plotter_processor.centerline_font.quality import score_quality, validate_strokes
from plotter_processor.centerline_font.route_assembler import assemble_component_route
from plotter_processor.centerline_font.route_planner import plan_glyph_routes
from plotter_processor.centerline_font.route_quality import routing_metrics
from plotter_processor.centerline_font.serializer import (
    load_centerline_font,
    write_centerline_font_atomic,
)
from plotter_processor.centerline_font.skeleton_selector import select_best_skeleton
from plotter_processor.font_loader import load_font


def compile_centerline_font(
    font_path: str | Path,
    chars: set[str] | list[str] | tuple[str, ...],
    config: CenterlineConfig,
    *,
    cache_path: Path | None = None,
    force: bool = False,
    strict_quality: bool = False,
    debug_dir: Path | None = None,
) -> tuple[CompiledCenterlineFont, Path]:
    source = Path(font_path)
    digest = font_sha256(source)
    target = cache_path or default_cache_path(digest, config)
    compiled: CompiledCenterlineFont | None = None
    if target.is_file() and not force:
        try:
            cached, cached_config = load_centerline_font(target)
            if cached.font_sha256 == digest and cached_config == config.serializable():
                compiled = cached
                compiled.font_path = source
        except (TypeError, ValueError):
            compiled = None
    requested = sorted({char for char in chars if not char.isspace()}, key=ord)
    with load_font(source) as font:
        if compiled is None:
            compiled = CompiledCenterlineFont(
                source,
                digest,
                font.metrics.units_per_em,
                font.metrics.ascent,
                font.metrics.descent,
                font.metrics.line_gap,
                {},
            )
        missing = [char for char in requested if char not in compiled.glyphs]
        compiled.cache_hits = len(requested) - len(missing)
        compiled.cache_misses = len(missing)
        for char in missing:
            try:
                glyph = _compile_glyph(source, char, font, config, debug_dir)
            except Exception as error:
                raise ValueError(
                    f'Centerline compilation failed for "{char}" (U+{ord(char):04X}): {error}'
                ) from error
            compiled.glyphs[char] = glyph
            if glyph.quality.get("needs_review"):
                compiled.warnings.append(f'Glyph "{char}" needs centerline review')
                if strict_quality or config.fail_on_low_quality:
                    raise ValueError(f'Centerline quality gate failed for "{char}"')
        if strict_quality or config.fail_on_low_quality:
            failed = [char for char in requested if compiled.glyphs[char].quality.get("needs_review")]
            if failed:
                chars_text = ", ".join(repr(char) for char in failed)
                raise ValueError(f"Centerline quality gate failed for cached glyphs: {chars_text}")
    write_centerline_font_atomic(compiled, target, config=config.serializable())
    return compiled, target


def _compile_glyph(
    source: Path,
    char: str,
    font,
    config: CenterlineConfig,
    debug_dir: Path | None,
) -> CenterlineGlyph:
    config = _config_for_glyph(config, char)
    raster = render_glyph(
        source,
        char,
        units_per_em=font.metrics.units_per_em,
        em_resolution_px=config.em_resolution_px,
        padding_px=config.padding_px,
        loaded_font=font,
    )
    mask = build_ink_mask(
        raster, threshold=config.threshold, closing_radius_px=config.closing_radius_px
    )
    selected = select_best_skeleton(mask, config)
    nodes, edges = list(selected.nodes), list(selected.edges)
    edge_geometry, warnings = build_smoothed_edge_geometry(nodes, edges, raster, config)
    routes = plan_glyph_routes(nodes, edges, config)
    strokes = [assemble_component_route(route, edge_geometry) for route in routes]
    validate_strokes(strokes)
    quality, quality_warnings = score_quality(
        mask,
        selected.skeleton,
        strokes,
        raster,
        min_coverage=config.min_mask_coverage,
        max_extra=config.max_reconstruction_extra,
        max_endpoint_factor=config.max_endpoint_factor,
    )
    quality.update(routing_metrics(edges, routes))
    quality.update(
        {
            "skeleton_method": selected.method,
            "candidate_scores": selected.candidate_scores,
            "candidate_metrics": selected.candidate_metrics,
            "graph_nodes": len(nodes),
            "junctions": sum(node.kind == "junction" for node in nodes),
            "spurs_removed": selected.simplification.spurs_removed,
            "junctions_merged": selected.simplification.junctions_merged,
            "false_junctions_removed": selected.simplification.false_junctions_removed,
            "duplicate_edges_removed": selected.simplification.duplicate_edges_removed,
            "micro_loops_removed": selected.simplification.micro_loops_removed,
        }
    )
    if float(quality["retrace_ratio"]) > config.max_retrace_ratio:
        quality_warnings.append(
            f"One-stroke retrace ratio {float(quality['retrace_ratio']):.3f} exceeds "
            f"configured limit {config.max_retrace_ratio:.3f}"
        )
        quality["needs_review"] = True
    if debug_dir is not None and (config.debug_enabled or quality.get("needs_review")):
        export_glyph_debug(
            debug_dir,
            raster,
            mask,
            selected.distance,
            selected.skeleton,
            selected.skeleton,
            nodes,
            edges,
            strokes,
            quality,
            candidate_skeletons=selected.candidate_skeletons,
        )
    return CenterlineGlyph(
        char,
        ord(char),
        raster.glyph_name,
        raster.advance_font_units,
        tuple(strokes),
        tuple(warnings + quality_warnings),
        quality,
    )


def _config_for_glyph(config: CenterlineConfig, char: str) -> CenterlineConfig:
    override = config.glyph_overrides.get(char)
    if not override:
        return config
    values: dict[str, object] = {}
    if "skeleton_method" in override:
        method = override["skeleton_method"]
        if method not in {"auto", "skeletonize", "medial_axis"}:
            raise ValueError(f"Invalid skeleton_method override for {char!r}")
        values["skeleton_method"] = method
    for key in (
        "simplify_tolerance_px",
        "min_branch_width_factor",
        "max_retrace_ratio",
    ):
        if key in override:
            value = override[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Invalid {key} override for {char!r}")
            values[key] = float(value)
    if "max_retrace_ratio" in values and float(values["max_retrace_ratio"]) > 1:
        raise ValueError(f"Invalid max_retrace_ratio override for {char!r}")
    return replace(config, **values)
