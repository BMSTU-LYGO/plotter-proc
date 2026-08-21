"""Manual release smoke for the complete conversion pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("build/manual-smoke"))
    parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    parser.add_argument("--font-mode", choices=("outline", "centerline"), default="centerline")
    parser.add_argument(
        "--document-layout", choices=("reflow", "hybrid", "preserve"), default="hybrid"
    )
    parser.add_argument("--layout-debug", action="store_true")
    args = parser.parse_args()
    result = run_pipeline(PipelineOptions(
        args.input,
        args.font,
        args.page,
        "normal",
        Path("configs/layout.yaml"),
        Path("configs/machine.yaml"),
        args.output_dir,
        font_mode=args.font_mode,
        document_layout=args.document_layout,
        layout_debug=args.layout_debug,
    ))
    if result.status != "ok":
        print(f"Smoke failed: {result.error}\nReport: {result.report_path}")
        return 1
    print(f"Smoke completed successfully. Report: {result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
