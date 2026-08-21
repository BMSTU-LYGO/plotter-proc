from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import (
    centerline_config_payload,
    default_cache_path,
    font_sha256,
    write_cache_metadata_atomic,
)
from plotter_processor.centerline_font.config import CenterlineConfig, _candidate_scoring
from plotter_processor.centerline_font.debug import export_glyph_debug
from plotter_processor.centerline_font.edge_geometry import build_smoothed_edge_geometry
from plotter_processor.centerline_font.glyph_patch import apply_glyph_patch, load_glyph_patch
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
    serialized_config = _serialized_config(config, digest)
    target = cache_path or default_cache_path(digest, config)
    compiled: CompiledCenterlineFont | None = None
    if target.is_file():
        try:
            cached, cached_config = load_centerline_font(target)
            if cached.font_sha256 == digest and cached_config == serialized_config:
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
        missing = requested if force else [char for char in requested if char not in compiled.glyphs]
        compiled.cache_hits = 0 if force else len(requested) - len(missing)
        compiled.cache_misses = len(missing)
        for char in missing:
            try:
                glyph = _compile_glyph(source, char, font, config, debug_dir, digest)
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
    if config.glyph_patch_file is not None:
        patches = load_glyph_patch(config.glyph_patch_file, digest)
        for char in requested:
            if char in patches:
                compiled.glyphs[char] = apply_glyph_patch(compiled.glyphs[char], patches[char])
    write_centerline_font_atomic(compiled, target, config=serialized_config)
    write_cache_metadata_atomic(
        target,
        font_hash=digest,
        font_path=source,
        config=config,
        glyph_count=len(compiled.glyphs),
    )
    return compiled, target


def _serialized_config(
    config: CenterlineConfig, font_digest: str | None = None
) -> dict[str, object]:
    return centerline_config_payload(config, font_hash=font_digest)


def _compile_glyph(
    source: Path,
    char: str,
    font,
    config: CenterlineConfig,
    debug_dir: Path | None,
    font_digest: str,
) -> CenterlineGlyph:
    config = _config_for_glyph(config, char, font_digest)
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
            "candidate_score_components": selected.candidate_score_components,
            "graph_nodes": len(nodes),
            "junctions": sum(node.kind == "junction" for node in nodes),
            "spurs_removed": selected.simplification.spurs_removed,
            "junctions_merged": selected.simplification.junctions_merged,
            "false_junctions_removed": selected.simplification.false_junctions_removed,
            "duplicate_edges_removed": selected.simplification.duplicate_edges_removed,
            "micro_loops_removed": selected.simplification.micro_loops_removed,
            "effective_config": config.serializable(),
        }
    )
    if float(quality["retrace_ratio"]) > config.max_retrace_ratio:
        quality_warnings.append(
            f"One-stroke retrace ratio {float(quality['retrace_ratio']):.3f} exceeds "
            f"configured limit {config.max_retrace_ratio:.3f}"
        )
        quality["needs_review"] = True
    if debug_dir is not None:
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


def _config_for_glyph(
    config: CenterlineConfig, char: str, font_digest: str | None = None
) -> CenterlineConfig:
    overrides = [config.glyph_overrides.get(char, {})]
    if font_digest is not None:
        overrides.append(config.font_overrides.get(font_digest.lower(), {}).get(char, {}))
    if not any(overrides):
        return config
    values: dict[str, object] = {}
    merged: dict[str, object] = {}
    for override in overrides:
        merged.update(override)
    if "skeleton_method" in merged:
        method = merged["skeleton_method"]
        if method not in {"auto", "skeletonize", "medial_axis"}:
            raise ValueError(f"Invalid skeleton_method override for {char!r}")
        values["skeleton_method"] = method
    if "candidate_methods" in merged:
        methods = merged["candidate_methods"]
        if (
            not isinstance(methods, list)
            or not methods
            or any(method not in {"skeletonize", "medial_axis"} for method in methods)
        ):
            raise ValueError(f"Invalid candidate_methods override for {char!r}")
        values["candidate_methods"] = tuple(methods)
    integer_ranges = {
        "em_resolution_px": (16, None),
        "padding_px": (0, None),
        "threshold": (1, 254),
        "closing_radius_px": (0, None),
        "max_junction_cluster_px": (1, None),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        if key not in merged:
            continue
        value = merged[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            raise ValueError(f"Invalid {key} override for {char!r}")
        values[key] = value
    for key in (
        "simplify_tolerance_px",
        "min_branch_width_factor",
        "max_micro_loop_width_factor",
        "spline_smoothing_factor",
        "output_step_px",
        "junction_max_angle_deg",
        "max_retrace_ratio",
    ):
        if key in merged:
            value = merged[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Invalid {key} override for {char!r}")
            values[key] = float(value)
    if "max_retrace_ratio" in values and float(values["max_retrace_ratio"]) > 1:
        raise ValueError(f"Invalid max_retrace_ratio override for {char!r}")
    if "output_step_px" in values and float(values["output_step_px"]) <= 0:
        raise ValueError(f"Invalid output_step_px override for {char!r}")
    if "junction_max_angle_deg" in values and float(values["junction_max_angle_deg"]) > 90:
        raise ValueError(f"Invalid junction_max_angle_deg override for {char!r}")
    if "candidate_scoring" in merged:
        raw = merged["candidate_scoring"]
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid candidate_scoring override for {char!r}")
        values["candidate_scoring"] = _candidate_scoring(raw)
    if "spur_pruning" in merged:
        raw = merged["spur_pruning"]
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid spur_pruning override for {char!r}")
        allowed = {
            "enabled",
            "max_coverage_loss",
            "preserve_connector_terminals",
            "preserve_counter_edges",
        }
        if set(raw) - allowed:
            raise ValueError(f"Invalid spur_pruning override for {char!r}")
        mapping = {
            "enabled": "spur_pruning_enabled",
            "max_coverage_loss": "spur_max_coverage_loss",
            "preserve_connector_terminals": "preserve_connector_terminals",
            "preserve_counter_edges": "preserve_counter_edges",
        }
        for key, field in mapping.items():
            if key in raw:
                values[field] = raw[key]
    return replace(config, **values)
