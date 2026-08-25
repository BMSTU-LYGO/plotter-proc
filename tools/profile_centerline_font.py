"""Cold centerline compiler profiler; intentionally not collected by pytest."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.config import load_yaml
from plotter_processor.performance import FunctionProfiler, collect_glyph_performance


def _unique_glyphs(text: str) -> list[str]:
    return sorted({char for char in text if not char.isspace()}, key=ord)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/layout.yaml"))
    parser.add_argument(
        "--glyph-count",
        choices=("1", "10", "all"),
        default="1",
        help="Profile one glyph, ten glyphs, or the complete corpus",
    )
    parser.add_argument(
        "--glyphs",
        help="Explicit glyph string; overrides --glyph-count and --corpus-file",
    )
    parser.add_argument(
        "--corpus-file", type=Path, default=Path("assets/font-cache-corpus.txt")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("build/profile-centerline-font.json")
    )
    parser.add_argument("--profile-top", type=int, default=20)
    parser.add_argument(
        "--workers", "--centerline-workers", dest="workers", default=1
    )
    args = parser.parse_args()
    if args.profile_top < 20:
        parser.error("--profile-top must be at least 20")

    corpus = args.glyphs
    if corpus is None:
        corpus = args.corpus_file.read_text(encoding="utf-8")
    glyphs = _unique_glyphs(corpus)
    if args.glyphs is None and args.glyph_count != "all":
        glyphs = glyphs[: int(args.glyph_count)]
    if not glyphs:
        parser.error("The selected glyph set is empty")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    profile_path = args.output.with_suffix(".prof")
    config = load_centerline_config(load_yaml(args.config))
    profiler = FunctionProfiler()
    with tempfile.TemporaryDirectory(prefix="plotter-cold-font-profile-") as temporary:
        cache_path = Path(temporary) / "centerlines.json"
        profiler.start()
        started = time.perf_counter()
        try:
            with collect_glyph_performance() as glyph_performance:
                compiled, _ = compile_centerline_font(
                    args.font,
                    set(glyphs),
                    config,
                    cache_path=cache_path,
                    force=True,
                    workers=args.workers,
                )
        finally:
            wall_ms = (time.perf_counter() - started) * 1000.0
            profiler.stop()

    profiler.dump(profile_path)
    payload = {
        "font": str(args.font),
        "config": str(args.config),
        "cold": True,
        "glyph_count": len(glyphs),
        "glyphs": glyph_performance.report(),
        "wall_ms": round(wall_ms, 3),
        "cache_hits": compiled.cache_hits,
        "cache_misses": compiled.cache_misses,
        "profile": {
            "stage": "font_compile",
            "stats_path": str(profile_path),
            "top_functions": profiler.top_functions(args.profile_top),
        },
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
