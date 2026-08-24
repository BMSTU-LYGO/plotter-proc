from __future__ import annotations

import atexit
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import (
    centerline_config_fingerprint,
    centerline_config_payload,
    default_cache_path,
    font_sha256,
    glyph_shard_path,
    load_shard_manifest,
    shard_identity,
    write_cache_metadata_atomic,
    write_shard_manifest_atomic,
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
from plotter_processor.performance import glyph_performance, measure_glyph_stage


def compile_centerline_font(
    font_path: str | Path,
    chars: set[str] | list[str] | tuple[str, ...],
    config: CenterlineConfig,
    *,
    cache_path: Path | None = None,
    force: bool = False,
    strict_quality: bool = False,
    debug_dir: Path | None = None,
    workers: str | int = 1,
) -> tuple[CompiledCenterlineFont, Path]:
    source = Path(font_path)
    digest = font_sha256(source)
    serialized_config = _serialized_config(config, digest)
    audit_fingerprint = centerline_config_fingerprint(config, font_hash=digest)
    target = cache_path or default_cache_path(digest, config)
    requested = sorted({char for char in chars if not char.isspace()}, key=ord)
    identity = shard_identity(digest, config)
    manifest = load_shard_manifest(target, identity=identity)
    compiled: CompiledCenterlineFont | None = None
    if manifest is None and target.is_file():
        try:
            cached, cached_config = load_centerline_font(target)
            if cached.font_sha256 == digest and cached_config == serialized_config:
                compiled = cached
                compiled.font_path = source
        except (TypeError, ValueError):
            compiled = None
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
        shard_chars = (
            sorted(set(manifest["glyphs"]), key=ord)
            if force and manifest is not None
            else requested
        )
        for char in shard_chars:
            shard = glyph_shard_path(target, char)
            if not shard.is_file():
                continue
            try:
                cached, cached_config = load_centerline_font(shard)
            except (TypeError, ValueError):
                continue
            if cached.font_sha256 == digest and cached_config == serialized_config:
                glyph = cached.glyphs.get(char)
                if glyph is not None:
                    compiled.glyphs[char] = glyph
        missing = requested if force else [char for char in requested if char not in compiled.glyphs]
        compiled.cache_hits = 0 if force else len(requested) - len(missing)
        compiled.cache_misses = len(missing)
        manifest_chars = set(manifest["glyphs"]) if manifest is not None else set()
        cached_chars = set(manifest_chars)
        cached_chars.update(compiled.glyphs)
        worker_count = resolve_centerline_worker_count(workers, len(missing))
        results: dict[str, CenterlineGlyph] = {}
        if worker_count == 1:
            for char in missing:
                try:
                    with glyph_performance(char):
                        results[char] = _compile_glyph(
                            source,
                            char,
                            font,
                            config,
                            debug_dir,
                            digest,
                            audit_fingerprint,
                        )
                except Exception as error:
                    raise _glyph_compile_error(char, error) from error
        elif missing:
            with ProcessPoolExecutor(
                max_workers=worker_count,
                initializer=_initialize_glyph_worker,
                initargs=(source, config, debug_dir, digest, audit_fingerprint),
            ) as executor:
                futures = {
                    executor.submit(_compile_glyph_in_worker, char): char
                    for char in missing
                }
                for future in as_completed(futures):
                    char = futures[future]
                    try:
                        results[char] = future.result()
                    except Exception as error:
                        raise _glyph_compile_error(char, error) from error
                    _write_glyph_shard(
                        compiled, results[char], target, serialized_config
                    )
                    cached_chars.add(char)
        for char in sorted(results, key=ord):
            glyph = results[char]
            compiled.glyphs[char] = glyph
            if worker_count == 1:
                _write_glyph_shard(compiled, glyph, target, serialized_config)
                cached_chars.add(char)
            if glyph.quality.get("needs_review"):
                warning = f'Glyph "{char}" needs centerline review'
                if warning not in compiled.warnings:
                    compiled.warnings.append(warning)
                if strict_quality or config.fail_on_low_quality:
                    raise ValueError(f'Centerline quality gate failed for "{char}"')
        if manifest is None or missing or cached_chars != manifest_chars:
            write_shard_manifest_atomic(
                target, identity=identity, glyphs=cached_chars
            )
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
    if manifest is None:
        write_centerline_font_atomic(compiled, target, config=serialized_config)
    if manifest is None or missing:
        write_cache_metadata_atomic(
            target,
            font_hash=digest,
            font_path=source,
            config=config,
            glyph_count=len(compiled.glyphs),
        )
    return compiled, target


def resolve_centerline_worker_count(requested: str | int, glyph_count: int) -> int:
    """Resolve a RAM-conscious process count for 2048 px/em raster work."""
    if isinstance(requested, bool):
        raise TypeError("centerline workers must be auto or a positive integer")
    if requested == "auto":
        count = min(os.cpu_count() or 1, 4)
    else:
        try:
            count = int(requested)
        except (TypeError, ValueError) as error:
            raise ValueError("centerline workers must be auto or a positive integer") from error
        if count < 1:
            raise ValueError("centerline workers must be auto or a positive integer")
    return max(1, min(count, max(1, glyph_count)))


_GLYPH_WORKER_FONT = None
_GLYPH_WORKER_SOURCE: Path | None = None
_GLYPH_WORKER_CONFIG: CenterlineConfig | None = None
_GLYPH_WORKER_DEBUG_DIR: Path | None = None
_GLYPH_WORKER_DIGEST: str | None = None
_GLYPH_WORKER_CONFIG_FINGERPRINT: str | None = None


def _initialize_glyph_worker(
    source: Path,
    config: CenterlineConfig,
    debug_dir: Path | None,
    digest: str,
    config_fingerprint: str,
) -> None:
    global _GLYPH_WORKER_FONT, _GLYPH_WORKER_SOURCE, _GLYPH_WORKER_CONFIG
    global _GLYPH_WORKER_DEBUG_DIR, _GLYPH_WORKER_DIGEST
    global _GLYPH_WORKER_CONFIG_FINGERPRINT
    _GLYPH_WORKER_SOURCE = source
    _GLYPH_WORKER_CONFIG = config
    _GLYPH_WORKER_DEBUG_DIR = debug_dir
    _GLYPH_WORKER_DIGEST = digest
    _GLYPH_WORKER_CONFIG_FINGERPRINT = config_fingerprint
    _GLYPH_WORKER_FONT = load_font(source)
    atexit.register(_GLYPH_WORKER_FONT.close)


def _compile_glyph_in_worker(char: str) -> CenterlineGlyph:
    if (
        _GLYPH_WORKER_FONT is None
        or _GLYPH_WORKER_SOURCE is None
        or _GLYPH_WORKER_CONFIG is None
        or _GLYPH_WORKER_DIGEST is None
        or _GLYPH_WORKER_CONFIG_FINGERPRINT is None
    ):
        raise RuntimeError("Centerline glyph worker is not initialized")
    return _compile_glyph(
        _GLYPH_WORKER_SOURCE,
        char,
        _GLYPH_WORKER_FONT,
        _GLYPH_WORKER_CONFIG,
        _GLYPH_WORKER_DEBUG_DIR,
        _GLYPH_WORKER_DIGEST,
        _GLYPH_WORKER_CONFIG_FINGERPRINT,
    )


def _write_glyph_shard(
    font: CompiledCenterlineFont,
    glyph: CenterlineGlyph,
    cache_path: Path,
    serialized_config: dict[str, object],
) -> None:
    shard_font = CompiledCenterlineFont(
        font.font_path,
        font.font_sha256,
        font.units_per_em,
        font.ascent,
        font.descent,
        font.line_gap,
        {glyph.char: glyph},
        [warning for warning in font.warnings if f'"{glyph.char}"' in warning],
    )
    write_centerline_font_atomic(
        shard_font, glyph_shard_path(cache_path, glyph.char), config=serialized_config
    )


def _glyph_compile_error(char: str, error: Exception) -> ValueError:
    return ValueError(
        f'Centerline compilation failed for "{char}" (U+{ord(char):04X}): {error}'
    )


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
    config_fingerprint: str | None = None,
) -> CenterlineGlyph:
    config = _config_for_glyph(config, char, font_digest)
    with measure_glyph_stage("render"):
        raster = render_glyph(
            source,
            char,
            units_per_em=font.metrics.units_per_em,
            em_resolution_px=config.em_resolution_px,
            padding_px=config.padding_px,
            loaded_font=font,
        )
    with measure_glyph_stage("mask"):
        mask = build_ink_mask(
            raster, threshold=config.threshold, closing_radius_px=config.closing_radius_px
        )
    selected = select_best_skeleton(
        mask,
        config,
        char=char,
        font_digest=font_digest,
        config_fingerprint=config_fingerprint,
    )
    nodes, edges = list(selected.nodes), list(selected.edges)
    with measure_glyph_stage("smoothing"):
        edge_geometry, warnings = build_smoothed_edge_geometry(nodes, edges, raster, config)
    with measure_glyph_stage("routing"):
        routes = plan_glyph_routes(nodes, edges, config)
        strokes = [assemble_component_route(route, edge_geometry) for route in routes]
        validate_strokes(strokes)
    with measure_glyph_stage("quality"):
        quality, quality_warnings = score_quality(
            mask,
            selected.skeleton,
            strokes,
            raster,
            min_coverage=config.min_mask_coverage,
            max_extra=config.max_reconstruction_extra,
            max_endpoint_factor=config.max_endpoint_factor,
            distance_map=selected.distance,
        )
        quality.update(routing_metrics(edges, routes))
    selected_metrics = selected.candidate_metrics[selected.method]
    quality.update(
        {
            "skeleton_method": selected.method,
            "candidate_scores": selected.candidate_scores,
            "candidate_metrics": selected.candidate_metrics,
            "candidate_score_components": selected.candidate_score_components,
            "candidate_fast_first": selected.fast_first,
            "candidate_confidence_checks": selected.confidence_checks,
            "candidate_methods_evaluated": selected.methods_evaluated,
            "candidate_methods_skipped": selected.methods_skipped,
            "graph_nodes": len(nodes),
            "junctions": sum(node.kind == "junction" for node in nodes),
            "short_edges": int(selected_metrics["short_edge_count"]),
            "micro_loops": int(selected_metrics["micro_loop_count"]),
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
