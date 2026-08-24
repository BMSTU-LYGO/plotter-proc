from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.cache import cache_status
from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.glyph_tuner import tune_glyphs
from plotter_processor.centerline_font.preview import export_centerline_font_preview
from plotter_processor.composition_pipeline import compose_manifest
from plotter_processor.config import load_yaml
from plotter_processor.document_reader import read_document
from plotter_processor.font_loader import load_font
from plotter_processor.gcode_exporter import (
    generate_calibration_gcode,
    generate_gcode,
    generate_pen_calibration_gcode,
    generate_speed_calibration_gcode,
    write_gcode_atomic,
)
from plotter_processor.job_comparison import compare_jobs
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.path_builder import load_path_document
from plotter_processor.pipeline import PipelineOptions, run_pipeline
from plotter_processor.presets import resolve_preset
from plotter_processor.unicode_coverage import inspect_coverage


class _ExplicitValue(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        del parser, option_string
        setattr(namespace, self.dest, values)
        setattr(namespace, f"{self.dest}_explicit", True)


def _pipeline_options(args: argparse.Namespace) -> PipelineOptions:
    preset = resolve_preset(
        args.preset,
        font_mode=args.font_mode if args.font_mode_explicit else None,
        connections=args.connections,
        workers=args.workers if args.workers_explicit else None,
        artifact_level=args.artifacts if args.artifacts_explicit else None,
        strict_centerline_quality=args.strict_centerline_quality,
    )
    return PipelineOptions(
        input_path=args.input,
        font_path=args.font,
        page=args.page,
        size=args.size,
        layout_config_path=args.layout_config,
        machine_config_path=args.machine_config,
        output_dir=args.output_dir,
        optimize_travel=not args.no_optimize_travel,
        font_mode=preset.font_mode,
        centerline_cache_path=args.centerline_cache,
        force_centerline_rebuild=args.force_centerline_rebuild,
        strict_centerline_quality=preset.strict_centerline_quality,
        motion_profile=args.motion_profile,
        latex=args.latex,
        latex_debug=args.latex_debug,
        latex_stroke_mode=args.latex_stroke_mode,
        strict_latex_quality=args.strict_latex_quality,
        pdf_math=args.pdf_math,
        math_debug=args.math_debug,
        join_writing=args.join_writing,
        layout_engine=args.layout_engine,
        connections=preset.connections,
        connection_debug=args.connection_debug,
        images=args.images,
        image_debug=args.image_debug,
        pdf_layout=args.pdf_layout,
        document_layout=args.document_layout,
        layout_debug=args.layout_debug,
        semantic_debug=args.semantic_debug,
        paginate=args.paginate,
        page_numbers=args.page_numbers,
        page_pause_seconds=args.page_pause_seconds,
        park_corner=args.park_corner,
        workers=preset.workers,
        artifact_level=preset.artifact_level,
        stage_cache_path=args.stage_cache,
        preset=preset.name,
    )


def _run(args: argparse.Namespace) -> int:
    result = run_pipeline(_pipeline_options(args))
    if result.status == "error":
        print(f"Error: {result.error}\nReport: {result.report_path}")
        return 1
    print(f"Processing completed successfully. Report: {result.report_path}")
    return 0


def _extract(args: argparse.Namespace) -> int:
    try:
        document = read_document(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(document.paragraphs), encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Extracted {len(document.paragraphs)} lines to {args.output}")
    return 0


def _font_info(args: argparse.Namespace) -> int:
    try:
        with load_font(args.font) as font:
            names = font.font.get("name")
            family = names.getDebugName(1) if names else None
            style = names.getDebugName(2) if names else None
            cyrillic = sum(0x0400 <= codepoint <= 0x04FF for codepoint in font.cmap)
            print(f"Path: {font.path}")
            print(f"Family: {family or 'unknown'}")
            print(f"Style: {style or 'unknown'}")
            print(f"unitsPerEm: {font.metrics.units_per_em}")
            print(
                f"Ascent/descent/lineGap: {font.metrics.ascent}/"
                f"{font.metrics.descent}/{font.metrics.line_gap}"
            )
            print(f"Glyph count: {len(font.glyph_set.keys())}")
            print(f"cmap count: {len(font.cmap)}")
            print(f"Cyrillic coverage: {cyrillic}/256")
            if args.coverage:
                coverage = inspect_coverage(font.cmap, args.coverage)
                print(
                    f"{args.coverage} symbols supported: "
                    f'{coverage["supported"]}/{coverage["total"]}'
                )
                missing = ", ".join(item["char"] for item in coverage["missing"])
                print(f"Missing common symbols: {missing or 'none'}")
                if args.json_output:
                    args.json_output.parent.mkdir(parents=True, exist_ok=True)
                    args.json_output.write_text(
                        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    return 0


def _gcode(args: argparse.Namespace) -> int:
    try:
        paths = load_path_document(args.input)
        machine = load_yaml(args.machine_config)
        gcode = generate_gcode(paths, machine)
        write_gcode_atomic(gcode, args.output)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"Error: {error}")
        return 1
    print(f"Saved G-code to {args.output}")
    return 0


def _calibrate(args: argparse.Namespace) -> int:
    try:
        machine = load_yaml(args.machine_config)
        gcode = generate_calibration_gcode(args.page, machine, full_page_frame=args.full_page_frame)
        write_gcode_atomic(gcode, args.output)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"Error: {error}")
        return 1
    print(f"Saved calibration G-code to {args.output}")
    return 0


def _motion_calibrate(args: argparse.Namespace) -> int:
    try:
        machine = load_yaml(args.machine_config)
        profile = resolve_motion_profile(machine, args.motion_profile)
        resolved = apply_motion_profile(machine, profile)
        generator = (
            generate_pen_calibration_gcode
            if args.command == "calibrate-pen"
            else generate_speed_calibration_gcode
        )
        write_gcode_atomic(generator(resolved), args.output)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"Error: {error}")
        return 1
    print(f"Saved {args.command} G-code to {args.output}")
    return 0


def _compare_jobs(args: argparse.Namespace) -> int:
    try:
        result = compare_jobs(args.baseline, args.candidate)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Saved comparison to {args.output}")
    return 0


def _compile_centerline(args: argparse.Namespace) -> int:
    try:
        config = load_centerline_config(load_yaml(args.layout_config))
        if args.cache_directory is not None:
            config = replace(config, cache_directory=args.cache_directory)
        chars = set(args.chars or "")
        if args.text_file:
            chars.update(args.text_file.read_text(encoding="utf-8"))
        if not chars:
            with load_font(args.font) as font:
                chars = {chr(codepoint) for codepoint in font.cmap}
        compiled, output = compile_centerline_font(
            args.font,
            chars,
            config,
            cache_path=args.output,
            force=args.force,
            strict_quality=args.strict_quality,
            debug_dir=args.debug_dir,
            workers=args.workers,
        )
        preview = args.preview or output.with_suffix(".svg")
        export_centerline_font_preview(compiled, sorted(chars, key=ord), preview)
    except (FileNotFoundError, OSError, TypeError, UnicodeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(
        f"Compiled {len(compiled.glyphs)} glyphs to {output}; "
        f"cache hits={compiled.cache_hits}, misses={compiled.cache_misses}; preview={preview}"
    )
    return 0


def _font_cache_info(args: argparse.Namespace) -> int:
    try:
        config = load_centerline_config(load_yaml(args.layout_config))
        if args.cache_directory is not None:
            config = replace(config, cache_directory=args.cache_directory)
        result = cache_status(args.font, config)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _tune_centerline(args: argparse.Namespace) -> int:
    try:
        config = load_centerline_config(load_yaml(args.layout_config))
        summary = tune_glyphs(
            args.font,
            args.chars,
            config,
            args.output_dir,
            max_candidates=args.max_candidates,
            top_n=args.top_n,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Saved centerline tuning summary to {summary}")
    return 0


def _compose(args: argparse.Namespace) -> int:
    result = compose_manifest(
        args.manifest,
        args.output_dir,
        layout_config_path=args.layout_config,
        machine_config_path=args.machine_config,
        connections=args.connections,
        motion_profile=args.motion_profile,
        latex=args.latex,
        latex_debug=args.latex_debug,
        latex_stroke_mode=args.latex_stroke_mode,
        strict_latex_quality=args.strict_latex_quality,
    )
    if result.status == "error":
        print(f"Error: {result.error}\nReport: {result.report_path}")
        return 1
    print(f"Composition completed successfully. Report: {result.report_path}")
    return 0


def _add_vector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    parser.add_argument("--preset", choices=("fast", "quality", "debug"))
    parser.add_argument("--no-optimize-travel", action="store_true")
    parser.add_argument(
        "--font-mode",
        choices=("outline", "centerline"),
        default="outline",
        action=_ExplicitValue,
    )
    parser.add_argument("--centerline-cache", type=Path)
    parser.add_argument("--stage-cache", type=Path)
    parser.add_argument("--force-centerline-rebuild", action="store_true")
    parser.add_argument("--strict-centerline-quality", action="store_true")
    parser.add_argument("--motion-profile", choices=("safe", "balanced", "fast"))
    parser.add_argument(
        "--join-writing", action="store_true", help="Join eligible centerline letters within words."
    )
    parser.add_argument("--layout-engine", choices=("legacy", "harfbuzz"))
    parser.add_argument("--connections", choices=("off", "safe", "aggressive"))
    parser.add_argument("--connection-debug", action="store_true")
    parser.add_argument("--images", choices=("auto", "outline", "centerline", "off"), default="auto")
    parser.add_argument("--image-debug", action="store_true")
    parser.add_argument("--pdf-layout", choices=("reflow", "preserve"))
    parser.add_argument("--document-layout", choices=("reflow", "hybrid", "preserve"))
    parser.add_argument("--layout-debug", action="store_true")
    parser.add_argument("--semantic-debug", action="store_true")
    parser.add_argument("--paginate", dest="paginate", action="store_true")
    parser.add_argument("--no-paginate", dest="paginate", action="store_false")
    parser.add_argument("--page-numbers", dest="page_numbers", action="store_true")
    parser.add_argument("--no-page-numbers", dest="page_numbers", action="store_false")
    parser.add_argument("--page-pause-seconds", type=float)
    parser.add_argument(
        "--park-corner",
        choices=("top_left", "top_right", "bottom_left", "bottom_right"),
    )
    parser.add_argument("--latex", choices=("auto", "mathtext", "off"), default="auto")
    parser.add_argument("--latex-debug", action="store_true")
    parser.add_argument("--latex-stroke-mode", choices=("centerline", "outline"))
    parser.add_argument("--strict-latex-quality", action="store_true")
    parser.add_argument("--pdf-math", choices=("auto", "visual", "off"), default="auto")
    parser.add_argument("--math-debug", action="store_true")
    parser.add_argument(
        "--workers",
        "--centerline-workers",
        dest="workers",
        default="auto",
        type=_workers_value,
        action=_ExplicitValue,
        metavar="auto|N",
        help="Page and centerline worker processes (default: auto, capped at 4).",
    )
    parser.add_argument(
        "--artifacts",
        choices=("minimal", "normal", "debug", "audit"),
        default="normal",
        action=_ExplicitValue,
        help="Artifact level (default: normal; explicit value overrides preset).",
    )
    parser.set_defaults(
        paginate=None,
        page_numbers=None,
        font_mode_explicit=False,
        workers_explicit=False,
        artifacts_explicit=False,
    )


def _workers_value(value: str) -> str | int:
    if value == "auto":
        return value
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be auto or a positive integer") from error
    if count < 1:
        raise argparse.ArgumentTypeError("must be auto or a positive integer")
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plotter-processor",
        description="Convert TXT/DOCX/PDF text and a TTF font into vector paths and G-code.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Run the complete vector pipeline.")
    _add_vector_arguments(run_parser)
    run_parser.set_defaults(handler=_run)

    svg_parser = commands.add_parser("svg", help="Generate vector previews and paths.")
    _add_vector_arguments(svg_parser)
    svg_parser.set_defaults(handler=_run)

    extract_parser = commands.add_parser("extract", help="Extract text from TXT, DOCX or PDF.")
    extract_parser.add_argument("input", type=Path)
    extract_parser.add_argument("--output", type=Path, default=Path("build/extracted.txt"))
    extract_parser.set_defaults(handler=_extract)

    info_parser = commands.add_parser("font-info", help="Inspect a TTF font.")
    info_parser.add_argument("font", type=Path)
    info_parser.add_argument("--coverage")
    info_parser.add_argument("--json", dest="json_output", type=Path)
    info_parser.set_defaults(handler=_font_info)

    compile_parser = commands.add_parser(
        "compile-centerline-font", help="Compile ordinary TTF glyphs into centerline strokes."
    )
    compile_parser.add_argument("font", type=Path)
    compile_parser.add_argument("--chars")
    compile_parser.add_argument("--text-file", type=Path)
    compile_parser.add_argument("--output", type=Path)
    compile_parser.add_argument("--preview", type=Path)
    compile_parser.add_argument("--debug-dir", type=Path)
    compile_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    compile_parser.add_argument("--cache-directory", type=Path)
    compile_parser.add_argument("--force", action="store_true")
    compile_parser.add_argument("--strict-quality", action="store_true")
    compile_parser.add_argument(
        "--workers",
        "--centerline-workers",
        dest="workers",
        default="auto",
        type=_workers_value,
        metavar="auto|N",
    )
    compile_parser.set_defaults(handler=_compile_centerline)

    cache_info_parser = commands.add_parser(
        "font-cache-info", help="Inspect the reusable centerline cache for one TTF font."
    )
    cache_info_parser.add_argument("font", type=Path)
    cache_info_parser.add_argument(
        "--layout-config", type=Path, default=Path("configs/layout.yaml")
    )
    cache_info_parser.add_argument("--cache-directory", type=Path)
    cache_info_parser.set_defaults(handler=_font_cache_info)

    tune_parser = commands.add_parser(
        "tune-centerline-glyphs", help="Search a bounded centerline parameter grid."
    )
    tune_parser.add_argument("font", type=Path)
    tune_parser.add_argument("--chars", required=True)
    tune_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    tune_parser.add_argument("--output-dir", type=Path, required=True)
    tune_parser.add_argument("--max-candidates", type=int, default=24)
    tune_parser.add_argument("--top-n", type=int, default=3)
    tune_parser.set_defaults(handler=_tune_centerline)

    compose_parser = commands.add_parser("compose", help="Compose text and safe SVG line-art.")
    compose_parser.add_argument("manifest", type=Path)
    compose_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    compose_parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    compose_parser.add_argument("--output-dir", type=Path, required=True)
    compose_parser.add_argument(
        "--connections", choices=("off", "safe", "aggressive"), default="off"
    )
    compose_parser.add_argument(
        "--motion-profile", choices=("safe", "balanced", "fast"), default="safe"
    )
    compose_parser.add_argument("--latex", choices=("auto", "mathtext", "off"), default="auto")
    compose_parser.add_argument("--latex-debug", action="store_true")
    compose_parser.add_argument("--latex-stroke-mode", choices=("centerline", "outline"))
    compose_parser.add_argument("--strict-latex-quality", action="store_true")
    compose_parser.set_defaults(handler=_compose)

    gcode_parser = commands.add_parser(
        "gcode",
        help="Generate motion-equivalent G-code from paths JSON v2.",
    )
    gcode_parser.add_argument("input", type=Path)
    gcode_parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    gcode_parser.add_argument("--output", type=Path, default=Path("build/output.gcode"))
    gcode_parser.set_defaults(handler=_gcode)

    calibrate_parser = commands.add_parser("calibrate", help="Generate calibration G-code.")
    calibrate_parser.add_argument(
        "--machine-config", type=Path, default=Path("configs/machine.yaml")
    )
    calibrate_parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    calibrate_parser.add_argument("--output", type=Path, default=Path("build/calibration.gcode"))
    calibrate_parser.add_argument("--full-page-frame", action="store_true")
    calibrate_parser.set_defaults(handler=_calibrate)
    for name, default in (
        ("calibrate-speed", Path("build/calibration/speed-test.gcode")),
        ("calibrate-pen", Path("build/calibration/pen-height.gcode")),
    ):
        motion_parser = commands.add_parser(name, help=f"Generate safe {name} G-code.")
        motion_parser.add_argument(
            "--machine-config", type=Path, default=Path("configs/machine.yaml")
        )
        motion_parser.add_argument(
            "--motion-profile", choices=("safe", "balanced", "fast"), default="safe"
        )
        motion_parser.add_argument("--output", type=Path, default=default)
        motion_parser.set_defaults(handler=_motion_calibrate)
    compare_parser = commands.add_parser("compare-jobs", help="Compare job reports and geometry.")
    compare_parser.add_argument("baseline", type=Path)
    compare_parser.add_argument("candidate", type=Path)
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.set_defaults(handler=_compare_jobs)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
