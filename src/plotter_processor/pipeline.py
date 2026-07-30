import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from plotter_processor.config import load_yaml
from plotter_processor.document_reader import read_document
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.page_renderer import (
    PAGE_SIZES_MM,
    mm_to_px,
    render_page,
    save_rendered_page,
)
from plotter_processor.path_tracer import save_path_document, trace_skeleton
from plotter_processor.skeletonizer import save_skeleton, skeletonize_image
from plotter_processor.svg_exporter import export_svg
from plotter_processor.text_normalizer import normalize_document
from plotter_processor.validator import path_statistics, validate_font


@dataclass(slots=True)
class PipelineOptions:
    input_path: Path
    font_path: Path
    page: str
    size: str
    layout_config_path: Path
    machine_config_path: Path
    output_dir: Path


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
        layout = load_yaml(options.layout_config_path)
        machine = load_yaml(options.machine_config_path)
        validate_font(options.font_path)

        document = read_document(options.input_path)
        if not any(paragraph.strip() for paragraph in document.paragraphs):
            raise ValueError("Document contains no usable text")
        (output_dir / "extracted.txt").write_text(
            "\n".join(document.paragraphs),
            encoding="utf-8",
        )

        normalized = normalize_document(document)
        warnings.extend(normalized.warnings)
        rendered = render_page(
            normalized.paragraphs,
            options.font_path,
            options.page,
            options.size,
            layout,
        )
        warnings.extend(rendered.warnings)
        save_rendered_page(rendered, output_dir / "page.png")

        render_options = {"threshold": 180, "remove_small_objects_px": 4}
        margins = _mapping(layout, "margins_mm")
        bounds = (
            mm_to_px(_number(margins, "left"), rendered.dpi),
            mm_to_px(_number(margins, "top"), rendered.dpi),
            rendered.width_px - mm_to_px(_number(margins, "right"), rendered.dpi),
            rendered.height_px - mm_to_px(_number(margins, "bottom"), rendered.dpi),
        )
        skeleton = skeletonize_image(
            rendered.image,
            threshold=int(_number(render_options, "threshold")),
            remove_small_objects_px=int(_number(render_options, "remove_small_objects_px")),
            content_bounds=bounds,
        )
        save_skeleton(skeleton, output_dir / "skeleton.png")

        trace_options = {"simplify_epsilon_px": 0.8, "min_stroke_points": 2}
        page_width_mm, page_height_mm = PAGE_SIZES_MM[options.page]
        paths = trace_skeleton(
            skeleton,
            dpi=rendered.dpi,
            page_width_mm=page_width_mm,
            page_height_mm=page_height_mm,
            simplify_epsilon_px=_number(trace_options, "simplify_epsilon_px"),
            min_stroke_points=int(_number(trace_options, "min_stroke_points")),
        )
        warnings.extend(paths.warnings)
        paths.warnings = list(dict.fromkeys(warnings))
        save_path_document(paths, rendered.dpi, output_dir / "paths.json")
        export_svg(paths, output_dir / "preview.svg", margins_mm=margins)

        statistics = path_statistics(paths)
        feedrates = _mapping(machine, "feedrate_mm_min")
        statistics.update(
            {
                "characters": len("\n".join(normalized.paragraphs)),
                "paragraphs": len(normalized.paragraphs),
                "skeleton_pixels": int(np.count_nonzero(skeleton)),
                "estimated_time_minutes": round(
                    float(statistics["draw_distance_mm"]) / _number(feedrates, "draw")
                    + float(statistics["travel_distance_mm"]) / _number(feedrates, "travel"),
                    3,
                ),
            }
        )

        gcode = generate_gcode(paths, machine)
        write_gcode_atomic(gcode, gcode_path)
        report = {
            "status": "ok",
            "input": str(options.input_path),
            "page": options.page,
            "size": options.size,
            "statistics": statistics,
            "warnings": paths.warnings,
            "outputs": {
                "extracted": str(output_dir / "extracted.txt"),
                "page": str(output_dir / "page.png"),
                "skeleton": str(output_dir / "skeleton.png"),
                "paths": str(output_dir / "paths.json"),
                "preview": str(output_dir / "preview.svg"),
                "gcode": str(gcode_path),
            },
        }
        _write_report(report_path, report)
        return PipelineResult(status="ok", report_path=report_path)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        gcode_path.unlink(missing_ok=True)
        _write_report(
            report_path,
            {
                "status": "error",
                "error": str(error),
                "warnings": list(dict.fromkeys(warnings)),
            },
        )
        return PipelineResult(status="error", report_path=report_path, error=str(error))


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _mapping(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a mapping")
    return value


def _number(config: dict[str, object], key: str) -> float:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    return float(value)
