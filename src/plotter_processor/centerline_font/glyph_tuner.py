from __future__ import annotations

import itertools
import json
from dataclasses import replace
from pathlib import Path

import yaml

from plotter_processor.centerline_font.compiler import compile_centerline_font
from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.preview import export_centerline_font_preview


def parameter_grid(config: CenterlineConfig, max_candidates: int) -> list[dict[str, object]]:
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    values = itertools.product(
        (config.threshold, max(1, config.threshold - 10), min(254, config.threshold + 10)),
        (0, 1, 2),
        (1.0, 1.5, 2.0),
        (0.7, 1.0),
        (0.02, 0.04),
        ("skeletonize", "medial_axis"),
    )
    keys = (
        "threshold",
        "closing_radius_px",
        "min_branch_width_factor",
        "simplify_tolerance_px",
        "spline_smoothing_factor",
        "skeleton_method",
    )
    return [dict(zip(keys, candidate, strict=True)) for candidate in itertools.islice(values, max_candidates)]


def tune_glyphs(
    font: Path,
    chars: str,
    config: CenterlineConfig,
    output_dir: Path,
    *,
    max_candidates: int = 24,
    top_n: int = 3,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid = parameter_grid(config, max_candidates)
    summary: dict[str, object] = {"version": 1, "max_candidates": max_candidates, "glyphs": {}}
    suggested: dict[str, object] = {"centerline": {"glyph_overrides": {}}}
    for char in dict.fromkeys(chars):
        results: list[tuple[float, int, dict[str, object], object]] = []
        failures: list[dict[str, object]] = []
        for index, override in enumerate(grid):
            effective = replace(config, glyph_overrides={char: override}, font_overrides={})
            try:
                compiled, _ = compile_centerline_font(
                    font,
                    {char},
                    effective,
                    cache_path=output_dir / char / f"candidate_{index:03d}.json",
                    force=True,
                )
                glyph = compiled.glyphs[char]
                scores = glyph.quality.get("candidate_score_components", {})
                method = str(glyph.quality.get("skeleton_method"))
                score = float(scores.get(method, {}).get("total", float("inf")))
                if glyph.quality.get("needs_review"):
                    score += 1000.0
                results.append((score, index, override, compiled))
            except (OSError, TypeError, ValueError) as error:
                failures.append({"index": index, "error": str(error)})
        results.sort(key=lambda item: (item[0], item[1]))
        if not results:
            raise ValueError(f"All tuning candidates failed for {char!r}")
        best = results[0]
        suggested["centerline"]["glyph_overrides"][char] = dict(best[2])  # type: ignore[index]
        previews: list[str] = []
        for rank, (score, index, override, compiled) in enumerate(results[:top_n], 1):
            preview = output_dir / char / f"top_{rank:02d}.svg"
            export_centerline_font_preview(compiled, [char], preview)
            previews.append(str(preview))
        summary["glyphs"][char] = {  # type: ignore[index]
            "evaluated": len(results),
            "failures": failures,
            "best_score": best[0],
            "best_candidate_index": best[1],
            "best_override": best[2],
            "previews": previews,
        }
    target = output_dir / "summary.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "suggested_overrides.yaml").write_text(
        yaml.safe_dump(suggested, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    return target
