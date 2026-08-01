from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_path_builder import build_centerline_paths
from plotter_processor.composition_models import SvgElement, TextElement
from plotter_processor.composition_reader import read_composition
from plotter_processor.config import load_yaml
from plotter_processor.font_fallback import FontSource, select_font_for_cluster
from plotter_processor.font_loader import load_font
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.handwriting import load_joining_config, route_words
from plotter_processor.latex_layout import layout_latex_paragraph
from plotter_processor.latex_parser import contains_latex
from plotter_processor.latex_renderer import math_renderer_from_options
from plotter_processor.models import PageSpec, PathDocument, Point, PositionedGlyph
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.path_builder import build_paths, save_path_document
from plotter_processor.path_simplifier import simplify_path_document
from plotter_processor.svg_exporter import export_plotter_preview
from plotter_processor.svg_importer import import_svg
from plotter_processor.validator import validate_path_document


@dataclass(frozen=True, slots=True)
class CompositionResult:
    status: str
    report_path: Path
    error: str | None = None


def compose_manifest(
    manifest_path: Path,
    output_dir: Path,
    *,
    layout_config_path: Path = Path("configs/layout.yaml"),
    machine_config_path: Path = Path("configs/machine.yaml"),
    connections: str = "off",
    motion_profile: str | None = None,
    latex: str = "auto",
    latex_debug: bool = False,
    latex_stroke_mode: str | None = None,
    strict_latex_quality: bool = False,
) -> CompositionResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path, gcode_path = output_dir / "report.json", output_dir / "output.gcode"
    try:
        document = read_composition(manifest_path)
        layout_config = load_yaml(layout_config_path)
        if latex not in {"auto", "mathtext", "off"}:
            raise ValueError(f"Unknown LaTeX mode: {latex}")
        latex_enabled = latex != "off" and bool(
            layout_config.get("latex", {}).get("enabled", True)
        )
        machine = load_yaml(machine_config_path)
        resolved_motion = resolve_motion_profile(machine, motion_profile)
        machine = apply_motion_profile(machine, resolved_motion)
        width, height = {"A4": (210.0, 297.0), "A5": (148.0, 210.0)}[document.page]
        page = PageSpec(document.page, width, height)
        strokes = []
        fallback_count = 0
        elements_report = []
        latex_expressions = 0
        warnings: list[str] = []
        for element in document.elements:
            _check_bounds(element.placement, page)
            if isinstance(element, SvgElement):
                height_mm = element.placement.height_mm or element.placement.width_mm
                added = import_svg(
                    element.path,
                    x_mm=element.placement.x_mm,
                    y_mm=element.placement.y_mm,
                    width_mm=element.placement.width_mm,
                    height_mm=height_mm,
                    fit=element.fit,
                    element_id=element.id,
                )
                for stroke in added:
                    stroke.element_id = element.id
                    stroke.element_type = "svg"
                    stroke.source_path = str(element.path)
                strokes.extend(added)
                elements_report.append({"id": element.id, "type": "svg", "strokes": len(added)})
            elif isinstance(element, TextElement):
                if latex_enabled and contains_latex(element.text):
                    previous_formula_index = latex_expressions
                    added, used_fallbacks, connection_metrics, latex_expressions = (
                        _latex_text_strokes(
                            document,
                            element,
                            page,
                            layout_config,
                            output_dir,
                            connections,
                            latex_debug=latex_debug,
                            formula_index_start=previous_formula_index,
                            latex_stroke_mode=latex_stroke_mode,
                            strict_latex_quality=strict_latex_quality,
                        )
                    )
                    formula_count = latex_expressions - previous_formula_index
                else:
                    added, used_fallbacks, connection_metrics = _text_strokes(
                        document, element, page, layout_config, output_dir, connections
                    )
                    formula_count = 0
                    if contains_latex(element.text):
                        warnings.append("latex_disabled_delimiters_left_literal")
                fallback_count += used_fallbacks
                strokes.extend(added)
                elements_report.append(
                    {
                        "id": element.id,
                        "type": "text",
                        "strokes": len(added),
                        "fallback_glyphs": used_fallbacks,
                        "connections": connection_metrics,
                        "latex_expressions": formula_count,
                    }
                )
        for index, stroke in enumerate(strokes):
            stroke.id = index
        paths = PathDocument(width, height, strokes, [], {"composition_version": 1})
        simplification = machine.get("path_simplification", {})
        if isinstance(simplification, dict) and simplification.get("enabled", False):
            deviations = simplification.get("max_deviation_mm", {})
            paths, _ = simplify_path_document(
                paths,
                duplicate_epsilon_mm=float(simplification.get("duplicate_epsilon_mm", 0.001)),
                min_segment_length_mm=float(simplification.get("min_segment_length_mm", 0.04)),
                max_deviation_mm=float(
                    deviations.get("centerline", 0.06) if isinstance(deviations, dict) else 0.06
                ),
            )
        # Connected cursive words legitimately combine several individually bounded glyph routes.
        validate_path_document(paths, max_points_per_contour=50_000)
        save_path_document(paths, output_dir / "paths.json")
        export_plotter_preview(paths, output_dir / "plotter-preview.svg")
        export_plotter_preview(paths, output_dir / "composition-preview.svg")
        export_plotter_preview(paths, output_dir / "font-source-preview.svg")
        gcode = generate_gcode(paths, machine)
        write_gcode_atomic(gcode, gcode_path)
        report = {
            "status": "ok",
            "composition": {
                "version": 1,
                "element_count": len(document.elements),
                "text_elements": sum(isinstance(e, TextElement) for e in document.elements),
                "svg_elements": sum(isinstance(e, SvgElement) for e in document.elements),
                "fallback_glyph_count": fallback_count,
                "missing_symbols": [],
                "unsafe_svg_features_rejected": [],
                "connections_mode": connections,
                "motion_profile": resolved_motion.name,
                "elements": elements_report,
                "latex": {
                    "enabled": latex_enabled,
                    "backend": "mathtext" if latex_enabled else "off",
                    "stroke_mode": latex_stroke_mode
                    or str(layout_config.get("latex", {}).get("stroke_mode", "centerline")),
                    "expressions_found": latex_expressions,
                    "rendered": latex_expressions,
                    "fallbacks": 0,
                    "unsupported": [
                        "full LaTeX documents and packages",
                        "TikZ, user macros, bibliography, and file includes",
                        "external LaTeX or shell execution",
                        "full OMML conversion",
                        "LaTeX reconstruction from PDF",
                    ],
                },
            },
            "warnings": list(dict.fromkeys(warnings)),
            "outputs": {
                "preview": str(output_dir / "composition-preview.svg"),
                "plotter_preview": str(output_dir / "plotter-preview.svg"),
                "font_source_preview": str(output_dir / "font-source-preview.svg"),
                "paths": str(output_dir / "paths.json"),
                "gcode": str(gcode_path),
            },
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return CompositionResult("ok", report_path)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        gcode_path.unlink(missing_ok=True)
        report_path.write_text(
            json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return CompositionResult("error", report_path, str(error))


def _text_strokes(document, element, page, layout_config, output_dir, connections):
    sizes = layout_config["sizes"]
    if element.size not in sizes:
        raise ValueError(f"Unknown text size: {element.size}")
    em_mm = float(sizes[element.size]["em_size_mm"])
    groups: dict[FontSource, list[PositionedGlyph]] = {}
    cursor = element.placement.x_mm
    fallback_count = 0
    glyph_index = 0
    word_index = 0
    for char in element.text:
        if char.isspace():
            cursor += em_mm * 0.33
            word_index += 1
            continue
        source = select_font_for_cluster(char, document.primary_font, list(document.fallback_fonts))
        fallback_count += source.role != "primary"
        with load_font(source.path) as font:
            scale = em_mm / font.metrics.units_per_em
            glyph_name = font.glyph_name_for_char(char)
            advance = font.advance_for_glyph(glyph_name) * scale
            baseline = element.placement.y_mm + font.metrics.ascent * scale
            if cursor + advance > element.placement.x_mm + element.placement.width_mm + 1e-9:
                raise ValueError(f"Text element {element.id!r} exceeds its width")
            groups.setdefault(source, []).append(
                PositionedGlyph(
                    char,
                    ord(char),
                    glyph_name,
                    cursor,
                    baseline,
                    advance,
                    scale,
                    0,
                    glyph_index,
                    word_index=word_index,
                )
            )
            cursor += advance
            glyph_index += 1
    output = []
    combined_metrics = {"connected_pairs": 0, "pen_lifts_saved": 0, "connector_draw_length_mm": 0.0}
    for source, glyphs in groups.items():
        with load_font(source.path) as font:
            if element.font_mode == "outline":
                paths = build_paths(font, glyphs, page, layout_config["vector"])
            elif element.font_mode == "centerline":
                config = load_centerline_config(layout_config)
                compiled, _ = compile_centerline_font(
                    source.path,
                    {glyph.char for glyph in glyphs},
                    config,
                    cache_path=output_dir / f".{source.sha256}.centerline-cache.json",
                )
                paths = build_centerline_paths(compiled, glyphs, page)
            else:
                raise ValueError(f"Unknown text font mode: {element.font_mode}")
        if element.font_mode == "centerline" and connections != "off":
            paths, metrics = route_words(
                paths,
                glyphs,
                load_joining_config(layout_config, enabled=True, mode=connections),
            )
            combined_metrics["connected_pairs"] += int(metrics["connected_pairs"])
            combined_metrics["pen_lifts_saved"] += int(metrics["pen_lifts_saved"])
            combined_metrics["connector_draw_length_mm"] += float(
                metrics["connector_draw_length_mm"]
            )
        for stroke in paths.strokes:
            stroke.element_id = element.id
            stroke.element_type = "text"
            stroke.font_role = source.role
            stroke.font_sha256 = source.sha256
        output.extend(paths.strokes)
    combined_metrics["connector_draw_length_mm"] = round(
        float(combined_metrics["connector_draw_length_mm"]), 6
    )
    return output, fallback_count, combined_metrics


def _latex_text_strokes(
    document,
    element,
    page,
    layout_config,
    output_dir,
    connections,
    *,
    latex_debug: bool,
    formula_index_start: int,
    latex_stroke_mode: str | None,
    strict_latex_quality: bool,
):
    sizes = layout_config["sizes"]
    if element.size not in sizes:
        raise ValueError(f"Unknown text size: {element.size}")
    latex_options = layout_config["latex"]
    with load_font(document.primary_font) as font:
        lines, formula_count = layout_latex_paragraph(
            element.text,
            font,
            element.placement.width_mm,
            sizes[element.size],
            latex_options,
            math_renderer_from_options(
                latex_options,
                stroke_mode=latex_stroke_mode,
                strict_quality=strict_latex_quality,
            ),
            formula_index_start=formula_index_start,
            element_id=element.id,
            debug_dir=output_dir / "latex-debug" if latex_debug else None,
        )
        cursor_y = element.placement.y_mm
        glyphs: list[PositionedGlyph] = []
        formulas = []
        for line in lines:
            cursor_y += line.spacing_before_mm
            for glyph in line.glyphs:
                glyphs.append(
                    PositionedGlyph(
                        glyph.char,
                        glyph.codepoint,
                        glyph.glyph_name,
                        element.placement.x_mm + glyph.x_mm,
                        cursor_y + glyph.baseline_y_mm,
                        glyph.advance_mm,
                        glyph.scale_mm_per_font_unit,
                        glyph.line_index,
                        len(glyphs),
                        glyph.word_index,
                        glyph.cluster_index,
                        glyph.font_id,
                        glyph.font_sha256,
                        glyph.x_offset_font_units,
                        glyph.y_offset_font_units,
                    )
                )
            for stroke in line.formula_strokes:
                formulas.append(
                    replace(
                        stroke,
                        points=[
                            Point(
                                element.placement.x_mm + point.x,
                                cursor_y + point.y,
                            )
                            for point in stroke.points
                        ],
                    )
                )
            cursor_y += line.advance_mm + line.spacing_after_mm
        maximum_y = (
            element.placement.y_mm + element.placement.height_mm
            if element.placement.height_mm is not None
            else page.height_mm
        )
        if cursor_y > maximum_y + 1e-9:
            raise ValueError(f"Text element {element.id!r} exceeds its height")
        if not glyphs:
            paths = PathDocument(page.width_mm, page.height_mm, [], [])
        elif element.font_mode == "outline":
            paths = build_paths(font, glyphs, page, layout_config["vector"])
        elif element.font_mode == "centerline":
            config = load_centerline_config(layout_config)
            compiled, _ = compile_centerline_font(
                document.primary_font,
                {glyph.char for glyph in glyphs},
                config,
                cache_path=output_dir / ".latex-centerline-cache.json",
            )
            paths = build_centerline_paths(compiled, glyphs, page)
        else:
            raise ValueError(f"Unknown text font mode: {element.font_mode}")
    metrics = {"connected_pairs": 0, "pen_lifts_saved": 0, "connector_draw_length_mm": 0.0}
    if element.font_mode == "centerline" and connections != "off" and glyphs:
        paths, metrics = route_words(
            paths,
            glyphs,
            load_joining_config(layout_config, enabled=True, mode=connections),
        )
    for stroke in paths.strokes:
        stroke.element_id = element.id
        stroke.element_type = "text"
        stroke.font_role = "primary"
    output = [*paths.strokes, *formulas]
    for index, stroke in enumerate(output):
        stroke.id = index
    return output, 0, metrics, formula_count


def _check_bounds(placement, page):
    height = placement.height_mm or 0.0
    if placement.x_mm + placement.width_mm > page.width_mm or placement.y_mm + height > page.height_mm:
        raise ValueError("Composition element lies outside page bounds")
