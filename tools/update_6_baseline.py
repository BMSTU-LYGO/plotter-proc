from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.preview import export_centerline_font_preview
from plotter_processor.config import load_yaml
from plotter_processor.pipeline import PipelineOptions, run_pipeline

PROBLEM_GLYPHS = "ъьы"
VISUAL_ROOT = Path("tests/visual/update_6")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _base_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _stroke_length(stroke) -> float:
    return sum(
        math.hypot(right.x - left.x, right.y - left.y)
        for left, right in zip(stroke.points, stroke.points[1:])
    )


def _glyph_metrics(glyph) -> dict[str, object]:
    quality = glyph.quality
    return {
        "skeleton_method": quality.get("skeleton_method"),
        "mask_coverage": quality.get("mask_coverage"),
        "reconstruction_extra": quality.get("reconstruction_extra"),
        "centerline_components": quality.get("centerline_components"),
        "graph_node_count": quality.get("graph_nodes"),
        "graph_edge_count": quality.get("graph_edges"),
        "junction_count": quality.get("junctions"),
        "endpoint_count": quality.get("endpoints"),
        "retrace_ratio": quality.get("retrace_ratio"),
        "stroke_count": len(glyph.strokes),
        "point_count": sum(len(stroke.points) for stroke in glyph.strokes),
        "route_length_font_units": round(sum(_stroke_length(s) for s in glyph.strokes), 6),
        "needs_review": bool(quality.get("needs_review")),
        "warnings": list(glyph.warnings),
    }


def _word_metrics(text: str) -> dict[str, object]:
    words = [word for word in text.split() if word]
    pairs = sum(max(0, len(word) - 1) for word in words)
    # Baseline has no inter-glyph route merge: every adjacent letter pair lifts the pen.
    return {
        "word_count": len(words),
        "letter_pairs": pairs,
        "pen_lifts_inside_words": pairs,
        "estimated_z_cycles": pairs,
        "connection_mode": "off",
    }


def _run_page(font: Path, input_path: Path, output_dir: Path, cache_path: Path) -> None:
    result = run_pipeline(
        PipelineOptions(
            input_path=input_path,
            font_path=font,
            page="A5",
            size="normal",
            layout_config_path=Path("configs/layout.yaml"),
            machine_config_path=Path("configs/machine.yaml"),
            output_dir=output_dir,
            font_mode="centerline",
            centerline_cache_path=cache_path,
        )
    )
    if result.status != "ok":
        raise RuntimeError(result.error or "baseline page pipeline failed")


def build_baseline(font: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = load_centerline_config(load_yaml(Path("configs/layout.yaml")))
    corpus_text = "\n".join(
        (VISUAL_ROOT / name).read_text(encoding="utf-8")
        for name in ("pacifico_problem_glyphs.txt", "pacifico_connections.txt")
    )
    cache_path = output_dir / "centerline-font.json"
    compiled, cache = compile_centerline_font(
        font,
        set(corpus_text),
        config,
        cache_path=cache_path,
        force=True,
        debug_dir=output_dir / "debug",
    )
    preview = output_dir / "centerline-preview.svg"
    export_centerline_font_preview(compiled, list(PROBLEM_GLYPHS), preview)
    problem_page = output_dir / "problem-glyphs-page"
    connections_page = output_dir / "connections-page"
    _run_page(font, VISUAL_ROOT / "pacifico_problem_glyphs.txt", problem_page, cache_path)
    _run_page(font, VISUAL_ROOT / "pacifico_connections.txt", connections_page, cache_path)
    connections_text = (VISUAL_ROOT / "pacifico_connections.txt").read_text(encoding="utf-8")
    metrics = {
        "schema_version": 1,
        "base_commit": _base_commit(),
        "font_sha256": _sha256(font),
        "problem_glyphs": {
            char: _glyph_metrics(compiled.glyphs[char]) for char in PROBLEM_GLYPHS
        },
        "word_connections": _word_metrics(connections_text),
        "symbols": {
            char: {"supported_by_primary": char in compiled.glyphs}
            for char in PROBLEM_GLYPHS
        },
        "artifacts": {
            "centerline_cache": str(cache),
            "centerline_preview": str(preview),
            "problem_page": str(problem_page),
            "connections_page": str(connections_page),
        },
    }
    target = output_dir / "baseline_metrics.json"
    target.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the reproducible UPD_Plotter_6 baseline")
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error(f"font does not exist: {args.font}")
    target = build_baseline(args.font, args.output_dir)
    print(f"Saved baseline metrics to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
