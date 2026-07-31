from __future__ import annotations

import json
import math
from pathlib import Path

from plotter_processor.path_builder import load_path_document


def compare_jobs(baseline_dir: Path, candidate_dir: Path) -> dict[str, object]:
    baseline_report = json.loads((baseline_dir / "report.json").read_text(encoding="utf-8"))
    candidate_report = json.loads((candidate_dir / "report.json").read_text(encoding="utf-8"))
    baseline = load_path_document(baseline_dir / "paths.json")
    candidate = load_path_document(candidate_dir / "paths.json")
    baseline_by_key = {_key(stroke): stroke for stroke in baseline.strokes}
    candidate_by_key = {_key(stroke): stroke for stroke in candidate.strokes}
    common = baseline_by_key.keys() & candidate_by_key.keys()
    deviation = max(
        (
            _stroke_deviation(baseline_by_key[key].points, candidate_by_key[key].points)
            for key in common
        ),
        default=0.0,
    )
    fields = (
        "stroke_count",
        "point_count",
        "draw_distance_mm",
        "travel_distance_mm",
        "total_z_distance_mm",
        "dwell_time_seconds",
        "ideal_total_time_seconds",
        "gcode_command_count",
    )
    changes = {
        field: round(
            float(candidate_report["motion"][field]) - float(baseline_report["motion"][field]), 6
        )
        for field in fields
    }
    return {
        "baseline": str(baseline_dir),
        "candidate": str(candidate_dir),
        "delta": changes,
        "max_path_deviation_mm": round(deviation, 6),
        "missing_strokes": len(baseline_by_key.keys() - candidate_by_key.keys()),
        "new_strokes": len(candidate_by_key.keys() - baseline_by_key.keys()),
        "changed_glyphs": sorted(
            {
                str(baseline_by_key[key].char)
                for key in common
                if _stroke_deviation(baseline_by_key[key].points, candidate_by_key[key].points)
                > 1e-9
            }
        ),
    }


def _key(stroke: object) -> tuple[object, ...]:
    return (stroke.glyph_index, stroke.char, stroke.contour_index, stroke.id)  # type: ignore[attr-defined]


def _stroke_deviation(left: list[object], right: list[object]) -> float:
    def directed(first: list[object], second: list[object]) -> float:
        return max(
            min(math.hypot(a.x - b.x, a.y - b.y) for b in second)  # type: ignore[attr-defined]
            for a in first
        )

    return max(directed(left, right), directed(right, left))
