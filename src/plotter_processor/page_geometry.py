from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from plotter_processor.handwriting import (
    JoiningConfig,
    VariationConfig,
    apply_variation,
    apply_word_width_variation,
    export_handwriting_debug,
    route_words,
)
from plotter_processor.models import PathDocument, PositionedGlyph
from plotter_processor.path_optimizer import RetraceConfig, optimize_paths
from plotter_processor.path_simplifier import (
    SimplificationTemplateCache,
    path_complexity,
    simplify_path_document,
)
from plotter_processor.performance import PagePerformance


@dataclass(slots=True)
class PageGeometryRequest:
    paths: PathDocument
    body_glyphs: list[PositionedGlyph]
    page_dir: Path
    page_metrics: PagePerformance
    optimize_travel: bool
    font_mode: str
    vector: dict[str, object]
    simplification_config: dict[str, object]
    variation_config: VariationConfig
    joining_config: JoiningConfig
    retrace_config: RetraceConfig
    connection_debug: bool
    simplification_template_cache: SimplificationTemplateCache


@dataclass(slots=True)
class PageGeometryResult:
    paths: PathDocument
    handwriting: dict[str, object]
    simplification: dict[str, object]
    stage_ms: dict[str, float]


def process_page_geometry(
    request: PageGeometryRequest,
    stage_progress: Callable[[str, str, float | None], None] | None = None,
) -> PageGeometryResult:
    """Apply path optimization, handwriting and simplification to one page."""
    paths = request.paths
    metrics = request.page_metrics
    metrics.values["stroke_count_before"] = len(paths.strokes)
    metrics.values["point_count_before"] = sum(
        len(stroke.points) for stroke in paths.strokes
    )
    if request.optimize_travel and _boolean(request.vector, "optimize_travel"):
        paths = optimize_paths(paths, request.retrace_config)

    stage_ms = {"handwriting": 0.0, "simplification": 0.0}
    handwriting: dict[str, object] = {"enabled": False}
    complexity_before_route = path_complexity(paths)
    if request.font_mode == "centerline" and request.body_glyphs:
        with _measure_stage("handwriting", stage_ms, stage_progress):
            with metrics.measure("variation_ms"):
                paths = apply_variation(
                    paths,
                    request.body_glyphs,
                    request.variation_config,
                    hotspots=metrics.hotspots,
                )
            complexity_before_route = path_complexity(paths)
            with metrics.measure("word_routing_ms"):
                paths, handwriting = route_words(
                    paths,
                    request.body_glyphs,
                    request.joining_config,
                    collect_debug=request.connection_debug,
                    hotspots=metrics.hotspots,
                    retrace_config=request.retrace_config,
                )
                paths = apply_word_width_variation(
                    paths, request.body_glyphs, request.variation_config
                )
            retrace = paths.metadata.get("safe_retrace")
            if isinstance(retrace, dict):
                handwriting.update(retrace)
        if request.joining_config.enabled and request.connection_debug:
            export_handwriting_debug(paths, request.page_dir / "connection-debug.svg")
        paths.metadata.pop("connection_debug", None)

    metrics.values["candidate_pairs"] = int(handwriting.get("pairs_total", 0))
    metrics.values["accepted_connections"] = int(handwriting.get("accepted", 0))
    simplification: dict[str, object] = {"enabled": False}
    if request.simplification_config.get("enabled", False):
        with (
            _measure_stage("simplification", stage_ms, stage_progress),
            metrics.measure("simplification_ms"),
        ):
            deviations = _mapping(
                request.simplification_config, "max_deviation_mm"
            )
            paths, simplification = simplify_path_document(
                paths,
                duplicate_epsilon_mm=_non_negative(
                    request.simplification_config, "duplicate_epsilon_mm"
                ),
                min_segment_length_mm=_non_negative(
                    request.simplification_config, "min_segment_length_mm"
                ),
                max_deviation_mm=_non_negative(deviations, request.font_mode),
                template_cache=request.simplification_template_cache,
                template_identities=(
                    {
                        glyph.glyph_index: (
                            glyph.font_sha256 or paths.metadata.get("font_sha256"),
                            glyph.char,
                            glyph.scale_mm_per_font_unit,
                        )
                        for glyph in request.body_glyphs
                    }
                    if not request.variation_config.enabled
                    else {}
                ),
                complexity_before_route=complexity_before_route,
                hotspots=metrics.hotspots,
            )
    return PageGeometryResult(paths, handwriting, simplification, stage_ms)


@contextmanager
def _measure_stage(
    stage: str,
    stage_ms: dict[str, float],
    progress: Callable[[str, str, float | None], None] | None,
) -> Iterator[None]:
    if progress is not None:
        progress(stage, "started", None)
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        stage_ms[stage] += elapsed_ms
        if progress is not None:
            progress(stage, "completed", elapsed_ms)


def _mapping(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"Missing or invalid mapping field: {key}")
    return value


def _boolean(config: dict[str, object], key: str) -> bool:
    value = config.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Missing or invalid boolean field: {key}")
    return value


def _non_negative(config: dict[str, object], key: str) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Missing or invalid non-negative field: {key}")
    return float(value)
