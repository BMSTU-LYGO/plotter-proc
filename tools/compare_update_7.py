from __future__ import annotations

import argparse
import json
from pathlib import Path

CASE_DIRECTORIES = {
    "latex/latex_complex-txt": "latex-complex",
    "latex/omml_basic-docx": "omml-basic",
    "latex/pdf_formula_text-pdf": "pdf-formula-text",
    "latex/pdf_formula_vector-pdf": "pdf-formula-vector",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline", type=Path, default=Path("build/update_7/baseline/baseline-summary.json")
    )
    parser.add_argument(
        "--candidate-root", type=Path, default=Path("build/update_7/candidate/block_1")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("build/update_7/candidate/block_1/comparison.json")
    )
    args = parser.parse_args()
    baseline = _json(args.baseline)
    baseline_cases = {
        case["name"]: case
        for case in baseline.get("cases", [])
        if isinstance(case, dict) and "name" in case
    }
    comparisons = []
    for baseline_name, directory in CASE_DIRECTORIES.items():
        candidate = _json(args.candidate_root / directory / "report.json")
        latex = candidate.get("latex", {})
        baseline_case = baseline_cases.get(baseline_name, {})
        baseline_geometry = baseline_case.get("geometry", {})
        formulas = latex.get("formulas", []) if isinstance(latex, dict) else []
        candidate_draw = sum(
            float(formula.get("quality", {}).get("draw_length_mm", 0.0))
            for formula in formulas
            if isinstance(formula, dict) and isinstance(formula.get("quality"), dict)
        )
        comparisons.append({
            "name": baseline_name,
            "baseline": {
                "status": baseline_case.get("status"),
                "formula_strokes": baseline_geometry.get("latex_strokes", 0),
                "formula_pen_lifts": baseline_geometry.get("latex_pen_lifts", 0),
                "formula_draw_length_mm": baseline_geometry.get("latex_draw_length_mm", 0),
                "outline_strokes": baseline_geometry.get("latex_outline_strokes", 0),
                "expressions": baseline_case.get("latex", {}).get("expressions_found", 0),
            },
            "candidate": {
                "status": candidate.get("status"),
                "formula_strokes": latex.get("strokes", 0),
                "formula_pen_lifts": latex.get("pen_lifts", 0),
                "formula_draw_length_mm": round(candidate_draw, 6),
                "outline_strokes": sum(
                    formula.get("stroke_mode") == "outline"
                    for formula in formulas
                    if isinstance(formula, dict)
                ),
                "expressions": latex.get("expressions_found", 0),
                "omml_expressions": latex.get("omml_expressions", 0),
                "pdf_visual_expressions": latex.get("pdf_visual_expressions", 0),
                "needs_review": latex.get("needs_review", 0),
            },
        })
    complex_case = comparisons[0]
    before = complex_case["baseline"]
    after = complex_case["candidate"]
    summary = {
        "base_commit": baseline.get("base_commit"),
        "cases": comparisons,
        "latex_complex": {
            "stroke_reduction_percent": _reduction(
                float(before["formula_strokes"]), float(after["formula_strokes"])
            ),
            "draw_length_reduction_percent": _reduction(
                float(before["formula_draw_length_mm"]),
                float(after["formula_draw_length_mm"]),
            ),
            "outline_strokes_before": before["outline_strokes"],
            "outline_strokes_after": after["outline_strokes"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved comparison to {args.output}")
    return 0


def _reduction(before: float, after: float) -> float:
    return round((before - after) / before * 100, 3) if before else 0.0


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
