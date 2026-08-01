from __future__ import annotations

import argparse
import json
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.preview import export_centerline_font_preview
from plotter_processor.centerline_font.visual_regression import glyph_snapshot
from plotter_processor.config import load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicitly update centerline geometry snapshots")
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--chars", required=True)
    parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("build/update_6/snapshots"))
    args = parser.parse_args()
    config = load_centerline_config(load_yaml(args.layout_config))
    compiled, _ = compile_centerline_font(
        args.font,
        set(args.chars),
        config,
        cache_path=args.output_dir / "centerline-font.json",
        force=True,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "geometry-snapshots.json"
    target.write_text(
        json.dumps(
            {char: glyph_snapshot(compiled.glyphs[char]) for char in args.chars},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    export_centerline_font_preview(compiled, list(args.chars), args.output_dir / "contact-sheet.svg")
    print(f"Updated centerline snapshots in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
