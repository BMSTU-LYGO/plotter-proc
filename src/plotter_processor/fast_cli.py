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
    args = parser.parse_args(argv)
    width, height = {"A5": (148.0, 210.0), "A4": (210.0, 297.0)}[args.page]
    result = run_fast_pipeline(
        args.input,
        args.cache,
        args.output_dir,
        machine_config_path=args.machine_config,
        layout_config=FastLayoutConfig(width, height, font_size_mm=args.font_size_mm),
    )
    print(f"pages={result.pages} report={result.report_path} total_ms={result.timings_ms['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
