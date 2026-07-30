from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from plotter_processor.config import load_yaml
from plotter_processor.document_reader import read_document
from plotter_processor.font_loader import load_font
from plotter_processor.gcode_exporter import (
    generate_calibration_gcode,
    generate_gcode,
    write_gcode_atomic,
)
from plotter_processor.path_builder import load_path_document
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _pipeline_options(args: argparse.Namespace) -> PipelineOptions:
    return PipelineOptions(
        input_path=args.input,
        font_path=args.font,
        page=args.page,
        size=args.size,
        layout_config_path=args.layout_config,
        machine_config_path=args.machine_config,
        output_dir=args.output_dir,
        optimize_travel=not args.no_optimize_travel,
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


def _add_vector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    parser.add_argument("--no-optimize-travel", action="store_true")


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
    info_parser.set_defaults(handler=_font_info)

    gcode_parser = commands.add_parser("gcode", help="Generate G-code from paths JSON v2.")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
