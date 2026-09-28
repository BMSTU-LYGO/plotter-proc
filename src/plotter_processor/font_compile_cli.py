from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml
from plotter_processor.font_loader import load_font


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plotter-font-compile",
        description="Offline compilation of TTF glyphs into a runtime-only centerline cache.",
    )
    parser.add_argument("font", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--text", type=Path, help="Compile only characters used by this UTF-8 file.")
    parser.add_argument("--chars", default="")
    parser.add_argument("--layout-config", type=Path, default=Path("configs/layout.yaml"))
    parser.add_argument("--workers", default="auto")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = replace(
        load_centerline_config(load_yaml(args.layout_config)),
        cache_directory=args.output.parent,
    )
    chars = set(args.chars)
    if args.text is not None:
        chars.update(args.text.read_text(encoding="utf-8"))
    if not chars:
        with load_font(args.font) as font:
            chars.update(chr(codepoint) for codepoint in font.cmap)
    compiled, output = compile_centerline_font(
        args.font,
        {char for char in chars if not char.isspace()},
        config,
        cache_path=args.output,
        force=args.force,
        workers=args.workers,
    )
    print(f"Compiled {len(compiled.glyphs)} glyphs to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
