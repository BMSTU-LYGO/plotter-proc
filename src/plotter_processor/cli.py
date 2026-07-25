import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from plotter_processor.config import load_yaml
from plotter_processor.document_reader import read_document
from plotter_processor.gcode_exporter import (
    generate_calibration_gcode,
    generate_gcode,
    write_gcode_atomic,
)
from plotter_processor.page_renderer import (
    PAGE_SIZES_MM,
    mm_to_px,
    render_page,
    save_rendered_page,
)
from plotter_processor.path_tracer import (
    load_path_document,
    save_path_document,
    trace_skeleton,
)
from plotter_processor.pipeline import PipelineOptions, run_pipeline
from plotter_processor.skeletonizer import save_skeleton, skeletonize_image
from plotter_processor.svg_exporter import export_svg


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"Command '{args.command}' is scaffolded but not implemented yet.")
    return 0


def _run(args: argparse.Namespace) -> int:
    result = run_pipeline(
        PipelineOptions(
            input_path=args.input,
            font_path=args.font,
            page=args.page,
            size=args.size,
            layout_config_path=args.layout_config,
            machine_config_path=args.machine_config,
            output_dir=args.output_dir,
        )
    )
    if result.status == "error":
        print(f"Error: {result.error}")
        print(f"Report: {result.report_path}")
        return 1
    print(f"Processing completed successfully. Report: {result.report_path}")
    return 0


def _extract(args: argparse.Namespace) -> int:
    try:
        document = read_document(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(document.paragraphs), encoding="utf-8")
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Error: {error}")
        return 1

    print(f"Extracted {len(document.paragraphs)} paragraphs to {args.output}")
    return 0


def _render(args: argparse.Namespace) -> int:
    try:
        paragraphs = args.input.read_text(encoding="utf-8").split("\n")
        config = load_yaml(args.layout_config)
        rendered = render_page(paragraphs, args.font, args.page, args.size, config)
        save_rendered_page(rendered, args.output)
    except (FileNotFoundError, OSError, TypeError, UnicodeError, ValueError) as error:
        print(f"Error: {error}")
        return 1

    print(f"Rendered {rendered.width_px}x{rendered.height_px} page to {args.output}")
    for warning in rendered.warnings:
        print(f"Warning: {warning}")
    return 0


def _trace(args: argparse.Namespace) -> int:
    try:
        config = load_yaml(args.layout_config)
        render_options = config.get("render")
        margins = config.get("margins_mm")
        if not isinstance(render_options, dict) or not isinstance(margins, dict):
            raise TypeError("Layout configuration must contain render and margins_mm mappings")
        dpi = config.get("dpi")
        if not isinstance(dpi, int):
            raise TypeError("Layout dpi must be an integer")

        with Image.open(args.input) as source:
            image = np.asarray(source.convert("L"))
        height, width = image.shape
        bounds = (
            mm_to_px(float(margins["left"]), dpi),
            mm_to_px(float(margins["top"]), dpi),
            width - mm_to_px(float(margins["right"]), dpi),
            height - mm_to_px(float(margins["bottom"]), dpi),
        )
        skeleton = skeletonize_image(
            image,
            threshold=int(render_options["threshold"]),
            remove_small_objects_px=int(render_options["remove_small_objects_px"]),
            content_bounds=bounds,
        )
        save_skeleton(skeleton, args.output)
        trace_options = config.get("trace", {})
        if not isinstance(trace_options, dict):
            raise TypeError("Layout trace configuration must be a mapping")
        page_width_mm, page_height_mm = PAGE_SIZES_MM[args.page]
        paths = trace_skeleton(
            skeleton,
            dpi=dpi,
            page_width_mm=page_width_mm,
            page_height_mm=page_height_mm,
            simplify_epsilon_px=float(trace_options.get("simplify_epsilon_px", 0.8)),
            min_stroke_points=int(trace_options.get("min_stroke_points", 2)),
        )
        save_path_document(paths, dpi, args.paths_output)
        export_svg(
            paths,
            args.preview_output,
            margins_mm=margins,
            show_travel=args.show_travel,
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as error:
        print(f"Error: {error}")
        return 1

    print(
        f"Traced {int(np.count_nonzero(skeleton))} skeleton pixels "
        f"into {len(paths.strokes)} strokes"
    )
    print(
        f"Saved skeleton to {args.output}, paths to {args.paths_output}, "
        f"and preview to {args.preview_output}"
    )
    return 0


def _gcode(args: argparse.Namespace) -> int:
    try:
        paths, _ = load_path_document(args.input)
        machine_config = load_yaml(args.machine_config)
        gcode = generate_gcode(paths, machine_config)
        write_gcode_atomic(gcode, args.output)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"Error: {error}")
        return 1

    command_count = sum(1 for line in gcode.splitlines() if line and not line.startswith(";"))
    print(f"Saved {command_count} G-code commands to {args.output}")
    return 0


def _calibrate(args: argparse.Namespace) -> int:
    try:
        machine_config = load_yaml(args.machine_config)
        gcode = generate_calibration_gcode(
            args.page,
            machine_config,
            full_page_frame=args.full_page_frame,
        )
        write_gcode_atomic(gcode, args.output)
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"Error: {error}")
        return 1

    print(f"Saved calibration G-code to {args.output}")
    print("Check all pen-up travel movements before allowing the pen to touch the page.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plotter-processor",
        description="Convert DOCX/PDF text into pen-plotter paths and Ender 3 G-code.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the complete processing pipeline.")
    run_parser.add_argument("input", type=Path)
    run_parser.add_argument("--font", type=Path, default=Path("assets/handwriting.ttf"))
    run_parser.add_argument("--page", choices=("A4", "A5"), default="A4")
    run_parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    run_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    run_parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    run_parser.add_argument("--output-dir", type=Path, default=Path("build"))
    run_parser.set_defaults(handler=_run)

    extract_parser = subparsers.add_parser("extract", help="Extract text from DOCX or PDF.")
    extract_parser.add_argument("input", type=Path)
    extract_parser.add_argument("--output", type=Path, default=Path("build/extracted.txt"))
    extract_parser.set_defaults(handler=_extract)

    render_parser = subparsers.add_parser("render", help="Render extracted text to a page image.")
    render_parser.add_argument("input", type=Path)
    render_parser.add_argument("--font", type=Path, default=Path("assets/handwriting.ttf"))
    render_parser.add_argument("--page", choices=("A4", "A5"), default="A4")
    render_parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    render_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    render_parser.add_argument("--output", type=Path, default=Path("build/page.png"))
    render_parser.set_defaults(handler=_render)

    trace_parser = subparsers.add_parser("trace", help="Trace a rendered page image.")
    trace_parser.add_argument("input", type=Path)
    trace_parser.add_argument("--page", choices=("A4", "A5"), default="A4")
    trace_parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    trace_parser.add_argument("--output", type=Path, default=Path("build/skeleton.png"))
    trace_parser.add_argument("--paths-output", type=Path, default=Path("build/paths.json"))
    trace_parser.add_argument("--preview-output", type=Path, default=Path("build/preview.svg"))
    trace_parser.add_argument("--show-travel", action="store_true")
    trace_parser.set_defaults(handler=_trace)

    gcode_parser = subparsers.add_parser("gcode", help="Generate G-code from paths JSON.")
    gcode_parser.add_argument("input", type=Path)
    gcode_parser.add_argument(
        "--machine-config", type=Path, default=Path("configs/machine.yaml")
    )
    gcode_parser.add_argument("--output", type=Path, default=Path("build/output.gcode"))
    gcode_parser.set_defaults(handler=_gcode)

    calibrate_parser = subparsers.add_parser(
        "calibrate", help="Generate safe machine calibration G-code."
    )
    calibrate_parser.add_argument(
        "--machine-config", type=Path, default=Path("configs/machine.yaml")
    )
    calibrate_parser.add_argument("--page", choices=("A4", "A5"), default="A4")
    calibrate_parser.add_argument("--output", type=Path, default=Path("build/calibration.gcode"))
    calibrate_parser.add_argument("--full-page-frame", action="store_true")
    calibrate_parser.set_defaults(handler=_calibrate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
