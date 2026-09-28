from __future__ import annotations

import argparse
from pathlib import Path

from plotter_processor.fast_layout import FastLayoutConfig
from plotter_processor.fast_pipeline import run_fast_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plotter-fast", description="Cache-only linear text pipeline.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    parser.add_argument("--page", choices=("A5", "A4"), default="A5")
    parser.add_argument("--font-size-mm", type=float, default=4.0)
    parser.add_argument("--margin-mm", type=float, default=2.0, help="Safe margin on every page edge (default: 2 mm).")
    parser.add_argument("--line-height-mm", type=float, help="Baseline spacing; defaults to a dense automatic value.")
    parser.add_argument(
        "--line-gap-mm",
        type=float,
        default=0.5,
        help="Clear vertical gap between line boxes (default: 0.5 mm).",
    )
    parser.add_argument("--word-spacing-mm", type=float, help="Word spacing; defaults to a dense automatic value.")
    parser.add_argument(
        "--max-gcode-commands",
        type=int,
        default=20_000_000,
        help="Safety limit for the combined output.gcode (default: 20000000).",
    )
    args = parser.parse_args(argv)
    width, height = {"A5": (148.0, 210.0), "A4": (210.0, 297.0)}[args.page]
    result = run_fast_pipeline(
        args.input,
        args.cache,
        args.output_dir,
        machine_config_path=args.machine_config,
        layout_config=FastLayoutConfig(
            page_width_mm=width,
            page_height_mm=height,
            margin_left_mm=args.margin_mm,
            margin_right_mm=args.margin_mm,
            margin_top_mm=args.margin_mm,
            margin_bottom_mm=args.margin_mm,
            font_size_mm=args.font_size_mm,
            line_height_mm=args.line_height_mm,
            word_spacing_mm=args.word_spacing_mm,
            line_gap_mm=args.line_gap_mm,
        ),
        max_gcode_commands=args.max_gcode_commands,
    )
    print(
        f"pages={result.pages} gcode={result.gcode_path} "
        f"report={result.report_path} total_ms={result.timings_ms['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
