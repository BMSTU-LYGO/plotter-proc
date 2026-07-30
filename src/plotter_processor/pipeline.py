from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.preview import export_centerline_font_preview
from plotter_processor.centerline_path_builder import build_centerline_paths
from plotter_processor.config import load_yaml
from plotter_processor.document_reader import read_document
from plotter_processor.font_loader import load_font
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.glyph_outline import extract_exact_outlines
from plotter_processor.models import PageSpec
from plotter_processor.path_builder import build_paths, path_statistics, save_path_document
from plotter_processor.path_optimizer import optimize_paths
from plotter_processor.svg_exporter import export_font_preview, export_plotter_preview
from plotter_processor.text_normalizer import normalize_document
from plotter_processor.validator import validate_page_spec, validate_path_document
from plotter_processor.vector_layout import layout_text


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


@dataclass(slots=True)
class PipelineResult:
    status: str
    report_path: Path
    error: str | None = None


def run_pipeline(options: PipelineOptions) -> PipelineResult:
    output_dir = options.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    gcode_path = output_dir / "output.gcode"
    warnings: list[str] = []
    try:
        layout_config = load_yaml(options.layout_config_path)
        if options.font_mode not in {"outline", "centerline"}:
            raise ValueError(f"Unknown font mode: {options.font_mode}")
        machine_config = load_yaml(options.machine_config_path)
        document = read_document(options.input_path)
        normalized = normalize_document(document)
        text = "\n".join(normalized.paragraphs)
        if not text.strip():
            raise ValueError("Document contains no usable text")
        extracted_path = output_dir / "extracted.txt"
        extracted_path.write_text(text, encoding="utf-8")
        warnings.extend(normalized.warnings)

        pages = _mapping(layout_config, "pages")
        page_values = _mapping(pages, options.page)
        page = PageSpec(
            options.page,
            _positive(page_values, "width_mm"),
            _positive(page_values, "height_mm"),
        )
        sizes = _mapping(layout_config, "sizes")
        size_options = _mapping(sizes, options.size)
        margins = _mapping(layout_config, "margins_mm")
        validate_page_spec(page, margins)
        vector = _mapping(layout_config, "vector")
        preview = _mapping(layout_config, "preview")
        layout_options = _mapping(layout_config, "layout")
        tab_spaces = _positive_int(layout_options, "tab_spaces")

        with load_font(options.font_path) as font:
            font.validate_text(text)
            layout = layout_text(
                normalized.paragraphs,
                font,
                page,
                margins,
                size_options,
                tab_spaces=tab_spaces,
            )
            warnings.extend(layout.warnings)
            outlines = extract_exact_outlines(font, layout.glyphs)
            export_font_preview(
                outlines,
                page.width_mm,
                page.height_mm,
                output_dir / "font-preview.svg",
                show_page_border=_boolean(preview, "show_page_border"),
            )
            if options.font_mode == "outline":
                paths = build_paths(font, layout.glyphs, page, vector)
                warnings.append("Outline mode follows both boundaries of filled TTF strokes")
                centerline_info = None
            else:
                centerline_config = load_centerline_config(layout_config)
                compiled, cache_path = compile_centerline_font(
                    options.font_path,
                    {glyph.char for glyph in layout.glyphs},
                    centerline_config,
                    cache_path=options.centerline_cache_path,
                    force=options.force_centerline_rebuild,
                    strict_quality=options.strict_centerline_quality,
                )
                paths = build_centerline_paths(compiled, layout.glyphs, page)
                export_centerline_font_preview(
                    compiled,
                    sorted({glyph.char for glyph in layout.glyphs}, key=ord),
                    output_dir / "centerline-font-preview.svg",
                )
                centerline_info = {
                    "compiled_glyphs": len(compiled.glyphs),
                    "cache_hits": compiled.cache_hits,
                    "cache_misses": compiled.cache_misses,
                    "needs_review": sum(
                        bool(glyph.quality.get("needs_review"))
                        for glyph in compiled.glyphs.values()
                    ),
                    "cache": str(cache_path),
                    "font_sha256": compiled.font_sha256,
                }

        warnings.extend(paths.warnings)
        if options.optimize_travel and _boolean(vector, "optimize_travel"):
            paths = optimize_paths(paths)
        paths.warnings = list(dict.fromkeys(warnings))
        validate_path_document(
            paths, max_points_per_contour=_positive_int(vector, "max_points_per_contour")
        )
        save_path_document(paths, output_dir / "paths.json")
        export_plotter_preview(
            paths,
            output_dir / "plotter-preview.svg",
            stroke_width_mm=_positive(preview, "plotter_stroke_width_mm"),
            show_page_border=_boolean(preview, "show_page_border"),
        )

        statistics = path_statistics(paths)
        feedrates = _mapping(machine_config, "feedrate_mm_min")
        statistics.update(
            {
                "characters": layout.character_count,
                "glyphs": len(layout.glyphs),
                "lines": layout.line_count,
                "estimated_time_minutes": round(
                    float(statistics["draw_distance_mm"]) / _positive(feedrates, "draw")
                    + float(statistics["travel_distance_mm"]) / _positive(feedrates, "travel"),
                    3,
                ),
            }
        )
        gcode = generate_gcode(paths, machine_config)
        _assert_safe_gcode(gcode)
        write_gcode_atomic(gcode, gcode_path)
        report = {
            "status": "ok",
            "pipeline": "ttf-centerline" if options.font_mode == "centerline" else "ttf-vector",
            "font_mode": options.font_mode,
            "input": str(options.input_path),
            "font": str(options.font_path),
            "page": options.page,
            "size": options.size,
            "shaping": "basic-cmap-hmtx",
            "statistics": statistics,
            "warnings": paths.warnings,
            "outputs": {
                "extracted": str(extracted_path),
                "font_preview": str(output_dir / "font-preview.svg"),
                "plotter_preview": str(output_dir / "plotter-preview.svg"),
                "paths": str(output_dir / "paths.json"),
                "gcode": str(gcode_path),
            },
        }
        if centerline_info is not None:
            report["centerline"] = centerline_info
            report["outputs"]["centerline_font_preview"] = str(
                output_dir / "centerline-font-preview.svg"
            )
        _write_report(report_path, report)
        return PipelineResult("ok", report_path)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        gcode_path.unlink(missing_ok=True)
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
            },
        )
        return PipelineResult("error", report_path, str(error))


def _assert_safe_gcode(gcode: str) -> None:
    for command in ("M104", "M109", "M140", "M190"):
        if command in gcode:
            raise ValueError(f"Unsafe heating command generated: {command}")
    if any(
        token.startswith("E") and token[1:].replace(".", "", 1).lstrip("-").isdigit()
        for line in gcode.splitlines()
        for token in line.split()
    ):
        raise ValueError("Unsafe extrusion command generated")


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
