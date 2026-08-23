from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.preview import export_centerline_font_preview
from plotter_processor.centerline_path_builder import build_centerline_paths
from plotter_processor.config import load_yaml
from plotter_processor.document_image_layout import save_document_structure
from plotter_processor.document_models import (
    SourceDocument,
    SourceParagraph,
    SourceRasterImageElement,
    SourceTableElement,
    SourceTextElement,
    SourceVectorElement,
)
from plotter_processor.document_paginator import add_page_numbers, paginate_document
from plotter_processor.font_loader import load_font
from plotter_processor.gcode_analyzer import analyze_gcode
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.glyph_outline import extract_exact_outlines
from plotter_processor.handwriting import (
    apply_variation,
    export_handwriting_debug,
    load_joining_config,
    load_variation_config,
    route_words,
)
from plotter_processor.job_exporter import save_job_manifest
from plotter_processor.job_models import PageJob, PlotterJob
from plotter_processor.latex_parser import contains_latex
from plotter_processor.models import PageSpec, PathDocument
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.motion_statistics import calculate_motion_statistics
from plotter_processor.multipage_gcode_exporter import generate_job_gcode
from plotter_processor.path_builder import build_paths, path_statistics, save_path_document
from plotter_processor.path_optimizer import optimize_paths
from plotter_processor.path_simplifier import simplify_path_document
from plotter_processor.performance import StageTimings
from plotter_processor.semantic_debug import export_semantic_debug
from plotter_processor.semantic_metrics import semantic_report
from plotter_processor.structured_document_reader import read_structured_document
from plotter_processor.svg_exporter import export_font_preview, export_plotter_preview
from plotter_processor.validator import (
    validate_page_spec,
    validate_page_workspace,
    validate_path_document,
)


@dataclass(slots=True)
class PipelineOptions:
    input_path: Path
    font_path: Path
    page: str
    size: str
    layout_config_path: Path
    machine_config_path: Path
    output_dir: Path
    optimize_travel: bool = True
    font_mode: str = "outline"
    centerline_cache_path: Path | None = None
    force_centerline_rebuild: bool = False
    strict_centerline_quality: bool = False
    motion_profile: str | None = None
    join_writing: bool = False
    layout_engine: str | None = None
    connections: str | None = None
    connection_debug: bool = False
    images: str = "auto"
    image_debug: bool = False
    pdf_layout: str | None = None
    document_layout: str | None = None
    layout_debug: bool = False
    semantic_debug: bool = False
    paginate: bool | None = None
    page_numbers: bool | None = None
    page_pause_seconds: float | None = None
    park_corner: str | None = None
    latex: str = "auto"
    latex_debug: bool = False
    latex_stroke_mode: str | None = None
    strict_latex_quality: bool = False
    pdf_math: str = "auto"
    math_debug: bool = False
    stage_progress: Callable[[str, str, float | None], None] | None = None


@dataclass(slots=True)
class PipelineResult:
    status: str
    report_path: Path
    error: str | None = None


def run_pipeline(options: PipelineOptions) -> PipelineResult:
    timings = StageTimings(options.stage_progress)
    output_dir = options.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    gcode_path = output_dir / "output.gcode"
    warnings: list[str] = []
    try:
        layout_config = load_yaml(options.layout_config_path)
        if options.font_mode not in {"outline", "centerline"}:
            raise ValueError(f"Unknown font mode: {options.font_mode}")
        if options.images not in {"auto", "outline", "centerline", "off"}:
            raise ValueError(f"Unknown image mode: {options.images}")
        if options.latex not in {"auto", "mathtext", "off"}:
            raise ValueError(f"Unknown LaTeX mode: {options.latex}")
        if options.latex_stroke_mode not in {None, "centerline", "outline"}:
            raise ValueError(f"Unknown LaTeX stroke mode: {options.latex_stroke_mode}")
        if options.pdf_math not in {"auto", "visual", "off"}:
            raise ValueError(f"Unknown PDF math mode: {options.pdf_math}")
        document_layout_options = _mapping(layout_config, "document_layout")
        configured_layout = str(document_layout_options.get("mode", "auto"))
        if configured_layout not in {"auto", "reflow", "hybrid", "preserve"}:
            raise ValueError(f"Unknown configured document layout: {configured_layout}")
        if (
            options.document_layout is not None
            and options.pdf_layout is not None
            and options.document_layout != options.pdf_layout
        ):
            raise ValueError(
                "--document-layout and --pdf-layout select different layout modes"
            )
        document_layout_mode = resolve_document_layout_mode(
            options.input_path,
            options.document_layout or options.pdf_layout,
            configured_layout,
        )
        machine_config = load_yaml(options.machine_config_path)
        motion_profile = resolve_motion_profile(machine_config, options.motion_profile)
        machine_config = apply_motion_profile(machine_config, motion_profile)
        _apply_page_change_overrides(machine_config, options)
        page_values = _mapping(_mapping(layout_config, "pages"), options.page)
        page = PageSpec(
            options.page,
            _positive(page_values, "width_mm"),
            _positive(page_values, "height_mm"),
        )
        margins = _mapping(layout_config, "margins_mm")
        validate_page_spec(page, margins)
        validate_page_workspace(page, machine_config)
        initial_latex_options = _mapping(layout_config, "latex")
        initial_pdf_math_options = initial_latex_options.get("pdf_math", {})
        if not isinstance(initial_pdf_math_options, dict):
            raise TypeError("latex.pdf_math must be a mapping")
        with timings.measure("read_document"):
            document = read_structured_document(
                options.input_path,
                assets_dir=output_dir / "extracted-assets",
                pdf_math_mode=options.pdf_math,
                pdf_math_options=dict(initial_pdf_math_options),
                math_debug_dir=output_dir / "latex-debug" if options.math_debug else None,
            )
        text = "\n".join(
            paragraph
            for element in document.elements
            if isinstance(element, SourceTextElement)
            for paragraph in element.paragraphs
        )
        extracted_path = output_dir / "extracted.txt"
        extracted_path.write_text(text, encoding="utf-8")
        warnings.extend(document.warnings)

        sizes = _mapping(layout_config, "sizes")
        size_options = _mapping(sizes, options.size)
        vector = _mapping(layout_config, "vector")
        preview = _mapping(layout_config, "preview")
        layout_options = _mapping(layout_config, "layout")
        paragraph_options = _mapping(layout_config, "paragraphs")
        table_options = _mapping(layout_config, "tables")
        image_options = _mapping(layout_config, "images")
        latex_options = _mapping(layout_config, "latex")
        pagination_options = dict(_mapping(layout_config, "pagination"))
        footer_options = dict(_mapping(pagination_options, "footer"))
        pagination_enabled = (
            bool(pagination_options.get("enabled", True))
            if options.paginate is None
            else options.paginate
        )
        page_numbers_enabled = (
            bool(footer_options.get("enabled", True))
            if options.page_numbers is None
            else options.page_numbers
        )
        if not page_numbers_enabled:
            footer_options["enabled"] = False
        pagination_options["footer"] = footer_options
        latex_mode = options.latex
        if latex_mode == "auto":
            latex_mode = "mathtext" if bool(latex_options.get("enabled", True)) else "off"
        if options.input_path.suffix.lower() == ".pdf":
            latex_mode = "mathtext" if options.pdf_math != "off" else "off"
        if latex_mode == "off" and any(
            contains_latex(paragraph)
            for element in document.elements
            if isinstance(element, SourceTextElement)
            for paragraph in element.paragraphs
        ):
            warnings.append("latex_disabled_delimiters_left_literal")
        engine = options.layout_engine or str(layout_options.get("engine", "legacy"))
        language = str(layout_options.get("language", "ru"))
        script = str(layout_options.get("script", "Cyrl"))
        direction = str(layout_options.get("direction", "ltr"))
        features = tuple(layout_options.get("features", []))

        with load_font(options.font_path) as font:
            with timings.measure("layout"):
                paginated = paginate_document(
                    document, font, page, margins, size_options, image_options,
                    pagination_options, enabled=pagination_enabled,
                    image_mode=options.images,
                    image_debug_dir=(
                        output_dir / "image-debug" if options.image_debug else None
                    ),
                    latex_mode=latex_mode, latex_options=latex_options,
                    latex_debug_dir=(
                        output_dir / "latex-debug"
                        if options.latex_debug or options.math_debug
                        else None
                    ),
                    latex_stroke_mode=options.latex_stroke_mode,
                    strict_latex_quality=options.strict_latex_quality,
                    document_layout_mode=document_layout_mode,
                    document_layout_options=document_layout_options,
                    paragraph_options=paragraph_options,
                    table_options=table_options,
                    layout_debug_dir=(
                        output_dir / "layout-debug" if options.layout_debug else None
                    ),
                    preserve_source_page_breaks=bool(
                        pagination_options.get("preserve_source_page_breaks", True)
                    ),
                    tab_spaces=_positive_int(layout_options, "tab_spaces"), engine=engine,
                    language=language, script=script, direction=direction,
                    features=features, stage_timings=timings,
                )
            warnings.extend(paginated.warnings)
            if page_numbers_enabled:
                number_size = str(footer_options.get("size", "small"))
                add_page_numbers(
                    paginated, font, page, margins, footer_options,
                    _mapping(sizes, number_size), engine=engine, language=language,
                    script=script, direction=direction, features=features,
                )
            page_count = len(paginated.pages)
            save_document_structure(
                document, output_dir / "document-structure.json",
                details=paginated.element_details, layout_mode=document_layout_mode,
            )
            number_indices = {
                (page_layout.page_index, index)
                for page_layout in paginated.pages
                for index in page_layout.metadata.get("page_number_glyph_indices", [])
            }
            body_glyphs = [
                glyph
                for page_layout in paginated.pages
                for glyph in page_layout.layout.glyphs
                if (page_layout.page_index, glyph.glyph_index) not in number_indices
            ]
            number_glyphs = [
                glyph
                for page_layout in paginated.pages
                for glyph in page_layout.layout.glyphs
                if (page_layout.page_index, glyph.glyph_index) in number_indices
            ]
            centerline_config = load_centerline_config(layout_config)
            compiled = None
            centerline_info = None
            cache_path = options.centerline_cache_path
            requested_centerline_chars = {glyph.char for glyph in number_glyphs}
            if options.font_mode == "centerline":
                requested_centerline_chars.update(glyph.char for glyph in body_glyphs)
            if requested_centerline_chars:
                with timings.measure("font_compile"):
                    compiled, cache_path = compile_centerline_font(
                        options.font_path,
                        requested_centerline_chars,
                        centerline_config,
                        cache_path=cache_path,
                        force=options.force_centerline_rebuild,
                        strict_quality=(
                            options.strict_centerline_quality
                            if options.font_mode == "centerline" else False
                        ),
                    )
                if options.font_mode == "centerline":
                    centerline_info = _centerline_report(
                        compiled, cache_path, [*body_glyphs, *number_glyphs]
                    )

            unique_preview_glyphs = list({
                (glyph.char, glyph.glyph_name): glyph
                for glyph in [*body_glyphs, *number_glyphs]
            }.values())
            with timings.measure("preview"):
                export_font_preview(
                    extract_exact_outlines(font, unique_preview_glyphs),
                    page.width_mm,
                    page.height_mm,
                    output_dir / "font-preview.svg",
                    show_page_border=_boolean(preview, "show_page_border"),
                )
                if compiled is not None:
                    export_centerline_font_preview(
                        compiled,
                        sorted(requested_centerline_chars, key=ord),
                        output_dir / "centerline-font-preview.svg",
                    )

            raw_pages: list[tuple[object, PathDocument, Path, list[object]]] = []
            for page_layout in paginated.pages:
                page_dir = (
                    output_dir if page_count == 1
                    else output_dir / "pages" / f"page-{page_layout.page_index + 1:03d}"
                )
                page_dir.mkdir(parents=True, exist_ok=True)
                page_number_set = set(page_layout.metadata.get("page_number_glyph_indices", []))
                body = [g for g in page_layout.layout.glyphs if g.glyph_index not in page_number_set]
                numbers = [g for g in page_layout.layout.glyphs if g.glyph_index in page_number_set]
                with timings.measure("build_paths"):
                    if options.font_mode == "outline":
                        paths = build_paths(font, body, page, vector)
                        warnings.append(
                            "Outline mode follows both boundaries of filled TTF strokes"
                        )
                    elif body and compiled is not None:
                        paths = build_centerline_paths(compiled, body, page)
                    else:
                        paths = PathDocument(page.width_mm, page.height_mm, [], [], {})
                if numbers and compiled is not None:
                    with timings.measure("build_paths"):
                        number_paths = build_centerline_paths(compiled, numbers, page)
                    for stroke in number_paths.strokes:
                        stroke.id = len(paths.strokes)
                        stroke.element_id = f"page-{page_layout.page_index + 1:03d}-number"
                        stroke.element_type = "page-number"
                        stroke.font_role = "page-number"
                        stroke.glyph_index = None
                        paths.strokes.append(stroke)
                for stroke in page_layout.graphic_strokes:
                    stroke.id = len(paths.strokes)
                    paths.strokes.append(stroke)
                if page_layout.graphic_strokes:
                    paths.metadata["pipeline"] = "document-mixed"
                raw_pages.append((page_layout, paths, page_dir, body))

        analysis_config = _mapping(machine_config, "motion_analysis")
        simplification_config = machine_config.get("path_simplification", {})
        joining_config = load_joining_config(
            layout_config,
            enabled=options.join_writing or options.connections not in {None, "off"},
            mode=options.connections,
        )
        page_jobs: list[PageJob] = []
        page_reports: list[dict[str, object]] = []
        handwriting_reports: list[dict[str, object]] = []
        simplification_reports: list[dict[str, object]] = []
        for page_layout, paths, page_dir, body_glyphs_for_page in raw_pages:
            warnings.extend(paths.warnings)
            if options.optimize_travel and _boolean(vector, "optimize_travel"):
                paths = optimize_paths(paths)
            handwriting: dict[str, object] = {"enabled": False}
            if options.font_mode == "centerline" and body_glyphs_for_page:
                with timings.measure("handwriting"):
                    paths = apply_variation(
                        paths, body_glyphs_for_page, load_variation_config(layout_config)
                    )
                    paths, handwriting = route_words(
                        paths, body_glyphs_for_page, joining_config
                    )
                    if joining_config.enabled and options.connection_debug:
                        export_handwriting_debug(paths, page_dir / "connection-debug.svg")
                    paths.metadata.pop("connection_debug", None)
            handwriting_reports.append(handwriting)
            simplification: dict[str, object] = {"enabled": False}
            if isinstance(simplification_config, dict) and simplification_config.get("enabled", False):
                with timings.measure("simplification"):
                    deviations = _mapping(simplification_config, "max_deviation_mm")
                    paths, simplification = simplify_path_document(
                        paths,
                        duplicate_epsilon_mm=_non_negative(
                            simplification_config, "duplicate_epsilon_mm"
                        ),
                        min_segment_length_mm=_non_negative(
                            simplification_config, "min_segment_length_mm"
                        ),
                        max_deviation_mm=_non_negative(deviations, options.font_mode),
                    )
            simplification_reports.append(simplification)
            paths.warnings = list(dict.fromkeys([*warnings, *page_layout.warnings]))
            validate_path_document(
                paths, max_points_per_contour=_positive_int(vector, "max_points_per_contour")
            )
            save_path_document(paths, page_dir / "paths.json")
            with timings.measure("preview"):
                export_plotter_preview(
                    paths, page_dir / "plotter-preview.svg",
                    stroke_width_mm=_positive(preview, "plotter_stroke_width_mm"),
                    show_page_border=_boolean(preview, "show_page_border"),
                )
            statistics = path_statistics(paths)
            motion = calculate_motion_statistics(
                paths, motion_profile,
                short_segment_mm=float(analysis_config.get("short_segment_mm", 0.2)),
                very_short_segment_mm=float(analysis_config.get("very_short_segment_mm", 0.08)),
            )
            statistics.update({
                "characters": page_layout.layout.character_count,
                "glyphs": len(page_layout.layout.glyphs),
                "lines": page_layout.layout.line_count,
                "estimated_time_minutes": motion["ideal_total_time_minutes"],
            })
            with timings.measure("gcode"):
                page_gcode = generate_gcode(
                    paths, machine_config, motion_profile=motion_profile, motion=motion
                )
                page_gcode = page_gcode.replace(
                    "; Generated by plotter-processor\n",
                    (
                        "; Generated by plotter-processor\n"
                        f"; Page {page_layout.page_index + 1}/{page_count}\n"
                    ),
                    1,
                )
                _assert_safe_gcode(
                    page_gcode,
                    allow_home=bool(_mapping(machine_config, "gcode").get("home", False)),
                )
                page_gcode_path = page_dir / (
                    "output.gcode" if page_count == 1 else "page.gcode"
                )
                write_gcode_atomic(page_gcode, page_gcode_path)
                analyzed = analyze_gcode(page_gcode)
            motion["gcode_command_count"] = analyzed["gcode_command_count"]
            motion["gcode_analysis"] = analyzed
            page_report = {
                "status": "ok", "page": page_layout.page_index + 1,
                "page_count": page_count, "statistics": statistics, "motion": motion,
                "handwriting": handwriting, "simplification": simplification,
                "source_element_ids": list(page_layout.source_element_ids),
                "warnings": paths.warnings,
            }
            if page_count > 1:
                _write_report(page_dir / "report.json", page_report)
            page_reports.append(page_report)
            page_jobs.append(PageJob(
                page_layout.page_index, page_layout.page_index + 1, paths,
                page_layout.source_element_ids, paths.warnings, dict(page_layout.metadata),
            ))

        page_change = _mapping(machine_config, "page_change")
        pause_seconds = _non_negative(page_change, "pause_seconds")
        job = PlotterJob(
            page, page_jobs, list(dict.fromkeys(warnings)),
            {"page_count": page_count, "pause_seconds": pause_seconds},
        )
        if page_count > 1:
            with timings.measure("gcode"):
                job_gcode = generate_job_gcode(
                    job, machine_config, motion_profile=motion_profile
                )
                _assert_safe_gcode(
                    job_gcode,
                    allow_home=bool(_mapping(machine_config, "gcode").get("home", False)),
                )
                write_gcode_atomic(job_gcode, gcode_path)
            with timings.measure("preview"):
                _export_job_preview(job, output_dir / "plotter-preview.svg", preview)
            save_job_manifest(job, output_dir / "job.json")
        else:
            save_job_manifest(job, output_dir / "job.json")

        total_motion_seconds = sum(
            float(report["motion"]["ideal_total_time_seconds"]) for report in page_reports
        )
        pause_count = max(0, page_count - 1)
        total_pause_seconds = pause_count * pause_seconds
        statistics = _aggregate_statistics(page_reports)
        motion = dict(page_reports[0]["motion"])
        motion.update({
            "ideal_motion_time_seconds": round(total_motion_seconds, 3),
            "page_change_pause_time_seconds": total_pause_seconds,
            "estimated_job_time_seconds": round(total_motion_seconds + total_pause_seconds, 3),
        })
        handwriting = (
            handwriting_reports[0] if page_count == 1 else _aggregate_handwriting(handwriting_reports)
        )
        if options.semantic_debug:
            export_semantic_debug(
                output_dir / "semantic-debug",
                page,
                [stroke for page_job in page_jobs for stroke in page_job.path_document.strokes],
            )
        semantic_metrics = _semantic_report(
            [stroke for page_job in page_jobs for stroke in page_job.path_document.strokes]
        )
        report = {
            "status": "ok",
            "pipeline": "ttf-centerline" if options.font_mode == "centerline" else "ttf-vector",
            "font_mode": options.font_mode,
            "input": str(options.input_path), "font": str(options.font_path),
            "page": options.page, "size": options.size, "shaping": engine,
            "statistics": statistics, "motion": motion,
            "simplification": simplification_reports[0], "handwriting": handwriting,
            "document_import": {
                **paginated.import_statistics,
                "layout_mode": document_layout_mode,
            },
            "document_layout": paginated.layout_statistics,
            "paragraph_formatting": _paragraph_formatting_report(document),
            "page_transform": paginated.layout_statistics.get("page_transform", {}),
            "layout_objects": paginated.layout_statistics.get("layout_objects", {}),
            "semantic_objects": {
                "underlines": paginated.import_statistics.get("underlines", 0),
                "generic_lines": paginated.import_statistics.get("generic_lines", 0),
                "arrows": paginated.import_statistics.get("arrows", 0),
                "tables": paginated.import_statistics.get("tables", 0),
                "table_cells": paginated.import_statistics.get("table_cells", 0),
                "table_pages": paginated.import_statistics.get("table_pages", 0),
                **semantic_metrics,
                "table_splits": paginated.import_statistics.get("table_splits", 0),
                "repeated_headers_emitted": paginated.import_statistics.get(
                    "repeated_headers_emitted", 0
                ),
                "shared_borders_suppressed": paginated.import_statistics.get(
                    "shared_borders_suppressed", 0
                ),
            },
            "latex": {
                **paginated.latex_statistics,
                "requested_mode": options.latex,
                "stroke_mode": options.latex_stroke_mode
                or str(latex_options.get("stroke_mode", "centerline")),
                "pdf_math_mode": options.pdf_math,
            },
            "pagination": {
                "enabled": pagination_enabled, "page_count": page_count,
                "page_numbers": page_numbers_enabled,
                "page_number_format": str(footer_options.get("format", "{page}")),
                "pause_seconds": pause_seconds, "pause_count": pause_count,
                "total_pause_seconds": total_pause_seconds,
                "park_mode": _mapping(page_change, "park").get("mode", "corner"),
                "park_corner": _mapping(page_change, "park").get("corner"),
            },
            "pages": [
                {
                    "page": index + 1,
                    "text_elements": sum(
                        isinstance(element, SourceTextElement)
                        for element in document.elements
                        if element.id in page_jobs[index].source_element_ids
                    ),
                    "image_elements": sum(
                        isinstance(element, (SourceRasterImageElement, SourceVectorElement))
                        for element in document.elements
                        if element.id in page_jobs[index].source_element_ids
                    ),
                    **page_report["statistics"],
                    "gcode": (
                        "output.gcode" if page_count == 1
                        else f"pages/page-{index + 1:03d}/page.gcode"
                    ),
                }
                for index, page_report in enumerate(page_reports)
            ],
            "warnings": list(dict.fromkeys(warnings)),
            "cache": {
                "font": {
                    "directory": str(centerline_config.cache_directory),
                    "hits": compiled.cache_hits if compiled is not None else 0,
                    "misses": compiled.cache_misses if compiled is not None else 0,
                    "rebuilt": compiled.cache_misses if compiled is not None else 0,
                    "algorithm_version": centerline_config.algorithm_version,
                },
                "images": {
                    "hits": paginated.import_statistics.get("image_cache_hits", 0),
                    "misses": paginated.import_statistics.get("image_cache_misses", 0),
                },
                "latex": {
                    "hits": paginated.latex_statistics.get("cache_hits", 0),
                    "misses": paginated.latex_statistics.get("cache_misses", 0),
                },
            },
            "outputs": {
                "extracted": str(extracted_path),
                "plotter_preview": str(output_dir / "plotter-preview.svg"),
                "gcode": str(gcode_path),
                "job": str(output_dir / "job.json"),
                "document_structure": str(output_dir / "document-structure.json"),
                "font_preview": str(output_dir / "font-preview.svg"),
            },
        }
        if compiled is not None:
            report["outputs"]["centerline_font_preview"] = str(
                output_dir / "centerline-font-preview.svg"
            )
        if options.latex_debug and paginated.latex_statistics.get("expressions_found", 0):
            report["outputs"]["latex_debug"] = str(output_dir / "latex-debug")
        if page_count == 1:
            report["outputs"].update({
                "paths": str(output_dir / "paths.json"),
            })
            if joining_config.enabled and options.connection_debug:
                report["outputs"]["connection_debug"] = str(
                    output_dir / "connection-debug.svg"
                )
                report["outputs"]["connection_debug_json"] = str(
                    output_dir / "connection-debug.json"
                )
        if centerline_info is not None:
            report["centerline"] = centerline_info
        if options.input_path.name == "benchmark_50_words.txt":
            report["benchmark_id"] = "benchmark_50_words_v1"
        with timings.measure("report"):
            json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        report["performance"] = timings.report()
        _write_report(report_path, report)
        return PipelineResult("ok", report_path)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        for stale_gcode in output_dir.rglob("*.gcode"):
            stale_gcode.unlink(missing_ok=True)
        _write_report(
            report_path,
            {
                "status": "error",
                "pipeline": (
                    "ttf-centerline" if options.font_mode == "centerline" else "ttf-vector"
                ),
                "font_mode": options.font_mode,
                "input": str(options.input_path),
                "font": str(options.font_path),
                "error": str(error),
                "warnings": list(dict.fromkeys(warnings)),
                "performance": timings.report(),
            },
        )
        return PipelineResult("error", report_path, str(error))


def _apply_page_change_overrides(
    machine_config: dict[str, object], options: PipelineOptions
) -> None:
    page_change = _mapping(machine_config, "page_change")
    if options.page_pause_seconds is not None:
        if options.page_pause_seconds < 0:
            raise ValueError("--page-pause-seconds must be non-negative")
        page_change["pause_seconds"] = options.page_pause_seconds
    if options.park_corner is not None:
        park = _mapping(page_change, "park")
        park["mode"] = "corner"
        park["corner"] = options.park_corner


def _paragraph_formatting_report(document: SourceDocument) -> dict[str, int]:
    paragraphs: list[SourceParagraph] = []
    for element in document.elements:
        if isinstance(element, SourceTextElement):
            paragraphs.extend(element.styled_paragraphs)
        elif isinstance(element, SourceTableElement):
            paragraphs.extend(
                paragraph
                for cell in element.cells
                for paragraph in cell.paragraphs
            )
    return {
        "paragraphs_total": len(paragraphs),
        "titles": sum(paragraph.semantic_role == "title" for paragraph in paragraphs),
        "headings": sum(
            (paragraph.semantic_role or "").startswith("heading")
            for paragraph in paragraphs
        ),
        "first_line_indents": sum(
            bool(paragraph.first_line_indent_mm)
            for paragraph in paragraphs
        ),
        "centered": sum(paragraph.alignment == "center" for paragraph in paragraphs),
        "right_aligned": sum(
            paragraph.alignment == "right" for paragraph in paragraphs
        ),
        "justified": sum(
            paragraph.alignment == "justify" for paragraph in paragraphs
        ),
        "custom_tab_stops": sum(bool(paragraph.tab_stops_mm) for paragraph in paragraphs),
    }


def _centerline_report(
    compiled: object,
    cache_path: Path | None,
    positioned_glyphs: list[object] | None = None,
) -> dict[str, object]:
    glyphs = compiled.glyphs
    graph_edges = sum(int(glyph.quality.get("graph_edges", 0)) for glyph in glyphs.values())
    routed_strokes = sum(len(glyph.strokes) for glyph in glyphs.values())
    retraced_font_units = sum(
        stroke.retraced_length_font_units
        for glyph in glyphs.values()
        for stroke in glyph.strokes
    )
    retraced_mm = sum(
        sum(stroke.retraced_length_font_units for stroke in glyphs[item.char].strokes)
        * item.scale_mm_per_font_unit
        for item in (positioned_glyphs or [])
        if item.char in glyphs
    )
    problematic = [
        glyph
        for glyph in glyphs.values()
        if glyph.quality.get("needs_review")
        or glyph.warnings
        or float(glyph.quality.get("retrace_ratio", 0.0)) > 0
    ]
    problematic.sort(
        key=lambda glyph: (
            not bool(glyph.quality.get("needs_review")),
            -float(glyph.quality.get("retrace_ratio", 0.0)),
            float(glyph.quality.get("mask_coverage", 1.0)),
            glyph.codepoint,
        )
    )
    return {
        "routing_strategy": "one_stroke_per_component",
        "compiled_glyphs": len(glyphs),
        "cache_hits": compiled.cache_hits,
        "cache_misses": compiled.cache_misses,
        "needs_review": sum(bool(glyph.quality.get("needs_review")) for glyph in glyphs.values()),
        "total_unique_glyphs": len(glyphs),
        "auto_passed": sum(
            not bool(glyph.quality.get("needs_review")) for glyph in glyphs.values()
        ),
        "failed": 0,
        "cache": str(cache_path) if cache_path else None,
        "font_sha256": compiled.font_sha256,
        "glyph_components": routed_strokes,
        "graph_edges_before_routing": graph_edges,
        "strokes_after_routing": routed_strokes,
        "pen_lifts_before_routing": graph_edges,
        "pen_lifts_after_routing": routed_strokes,
        "pen_lifts_saved": max(0, graph_edges - routed_strokes),
        "retraced_length_font_units": round(retraced_font_units, 6),
        "retraced_length_mm": round(retraced_mm, 6),
        "retraced_length_measured": positioned_glyphs is not None,
        "fallback_glyphs": [
            char for char, glyph in glyphs.items() if glyph.quality.get("fallback_used")
        ],
        "worst_glyphs": [
            {
                "glyph": glyph.char,
                "codepoint": f"U+{glyph.codepoint:04X}",
                "coverage": glyph.quality.get("mask_coverage"),
                "inside_mask": glyph.quality.get("centerline_inside_mask_ratio"),
                "components": glyph.quality.get("centerline_components"),
                "routes_before": glyph.quality.get("strokes_before_routing"),
                "routes_after": glyph.quality.get("strokes_after_routing"),
                "retrace_ratio": glyph.quality.get("retrace_ratio"),
                "method": glyph.quality.get("skeleton_method"),
                "quality_status": glyph.quality.get(
                    "quality_status",
                    "needs_review" if glyph.quality.get("needs_review") else "auto_passed",
                ),
                "warning": glyph.warnings[0] if glyph.warnings else None,
            }
            for glyph in problematic[:10]
        ],
    }


def _semantic_report(strokes: list[object]) -> dict[str, object]:
    return semantic_report(strokes)


def _aggregate_statistics(page_reports: list[dict[str, object]]) -> dict[str, object]:
    keys = (
        "contours", "strokes", "points", "closed_contours", "open_contours",
        "draw_distance_mm", "travel_distance_mm", "characters", "glyphs", "lines",
    )
    result: dict[str, object] = {}
    for key in keys:
        result[key] = round(
            sum(float(report["statistics"].get(key, 0)) for report in page_reports), 3
        )
    total_minutes = sum(
        float(report["statistics"].get("estimated_time_minutes", 0))
        for report in page_reports
    )
    result["estimated_time_minutes"] = total_minutes
    result["pages"] = len(page_reports)
    result["bounding_box_mm"] = None
    return result


def _aggregate_handwriting(reports: list[dict[str, object]]) -> dict[str, object]:
    reasons: dict[str, int] = {}
    for report in reports:
        values = report.get("rejections_by_reason", {})
        if isinstance(values, dict):
            for reason, count in values.items():
                reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
    totals = {
        "enabled": any(bool(report.get("enabled")) for report in reports),
        "mode": next((report.get("mode") for report in reports if report.get("mode")), "off"),
        "words": sum(int(report.get("words", 0)) for report in reports),
        "pairs_total": sum(int(report.get("pairs_total", 0)) for report in reports),
        "accepted": sum(int(report.get("accepted", 0)) for report in reports),
        "rejected": sum(int(report.get("rejected", 0)) for report in reports),
        "rejected_distance": sum(
            int(report.get("rejected_distance", 0)) for report in reports
        ),
        "rejected_tangent": sum(
            int(report.get("rejected_tangent", 0)) for report in reports
        ),
        "rejected_collision": sum(
            int(report.get("rejected_collision", 0)) for report in reports
        ),
        "rejected_corridor": sum(
            int(report.get("rejected_corridor", 0)) for report in reports
        ),
        "snapped_existing_contact": sum(
            int(report.get("snapped_existing_contact", 0)) for report in reports
        ),
        "connector_length_mm": round(
            sum(float(report.get("connector_length_mm", 0)) for report in reports), 6
        ),
        "joins_created": sum(int(report.get("joins_created", 0)) for report in reports),
        "joins_rejected": sum(int(report.get("joins_rejected", 0)) for report in reports),
        "pen_lifts_saved": sum(int(report.get("pen_lifts_saved", 0)) for report in reports),
        "rejections_by_reason": reasons,
    }
    return totals


def resolve_document_layout_mode(
    input_path: Path,
    explicit_mode: str | None,
    configured_mode: str,
) -> str:
    selected = explicit_mode or configured_mode
    if selected != "auto":
        return selected
    return "reflow" if input_path.suffix.lower() == ".txt" else "hybrid"


def _export_job_preview(
    job: PlotterJob, output_path: Path, preview_options: dict[str, object]
) -> None:
    stroke_width = _positive(preview_options, "plotter_stroke_width_mm")
    gap = 10.0
    total_height = len(job.pages) * job.page_spec.height_mm + (len(job.pages) - 1) * gap
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '
            f'{job.page_spec.width_mm} {total_height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for page_index, page_job in enumerate(job.pages):
        offset = page_index * (job.page_spec.height_mm + gap)
        lines.append(
            f'<rect x="0" y="{offset}" width="{job.page_spec.width_mm}" '
            f'height="{job.page_spec.height_mm}" fill="none" stroke="#888" stroke-width="0.2"/>'
        )
        lines.append(f'<g transform="translate(0 {offset})" fill="none" stroke="#111">')
        for stroke in page_job.path_document.strokes:
            points = " ".join(f"{point.x:.4f},{point.y:.4f}" for point in stroke.points)
            tag = "polygon" if stroke.closed else "polyline"
            lines.append(
                f'<{tag} points="{points}" stroke-width="{stroke_width}" '
                f'data-element-type="{stroke.element_type or "text"}"/>'
            )
        lines.append("</g>")
    lines.append("</svg>")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _assert_safe_gcode(gcode: str, *, allow_home: bool = False) -> None:
    for command in ("M104", "M109", "M140", "M190"):
        if command in gcode:
            raise ValueError(f"Unsafe heating command generated: {command}")
    if any(
        token.startswith("E") and token[1:].replace(".", "", 1).lstrip("-").isdigit()
        for line in gcode.splitlines()
        for token in line.split()
    ):
        raise ValueError("Unsafe extrusion command generated")
    if not allow_home and any(line.strip().startswith("G28") for line in gcode.splitlines()):
        raise ValueError("Unsafe homing command generated while gcode.home is disabled")


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mapping(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"Missing or invalid mapping field: {key}")
    return value


def _positive(config: dict[str, object], key: str) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: {key}")
    return float(value)


def _positive_int(config: dict[str, object], key: str) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Missing or invalid positive integer field: {key}")
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
