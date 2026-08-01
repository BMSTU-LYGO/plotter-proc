from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

BLOCKS = {"latex": "block_1", "images": "block_2", "lines_tables": "block_3"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reproducible UPD 7 baseline suite.")
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/update_7"))
    parser.add_argument(
        "--output-root", type=Path, default=Path("build/update_7/baseline")
    )
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--refresh-geometry", action="store_true")
    args = parser.parse_args()
    font = args.font.resolve()
    if not font.is_file():
        raise FileNotFoundError(f"Font not found: {font}")
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if "candidate" in output_root.parts:
        raise ValueError("Baseline runner refuses to write inside a candidate directory")
    if args.refresh_geometry:
        _refresh_geometry(output_root)
        return 0

    cases = []
    for source in sorted(path for path in args.fixtures.rglob("*") if path.is_file()):
        group = source.relative_to(args.fixtures).parts[0]
        block = BLOCKS.get(group)
        if block is None:
            continue
        relative = source.relative_to(args.fixtures / group)
        case_name = f"{relative.with_suffix('').as_posix()}-{relative.suffix.lstrip('.')}"
        case_output = output_root / block / case_name
        case_output.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "plotter_processor",
            "run",
            str(source.resolve()),
            "--font",
            str(font),
            "--font-mode",
            "centerline",
            "--page",
            "A5",
            "--paginate",
            "--latex",
            "auto",
            "--images",
            "outline",
            "--centerline-cache",
            str(output_root / "shared-font-cache.json"),
            "--output-dir",
            str(case_output),
        ]
        started = time.perf_counter()
        environment = dict(os.environ)
        environment.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")
        print(f"Running {group}/{case_name}...", flush=True)
        try:
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=args.timeout_seconds,
            )
            returncode = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as error:
            returncode = 124
            stdout = _timeout_text(error.stdout)
            stderr = _timeout_text(error.stderr) + (
                f"\nTimed out after {args.timeout_seconds:.1f} seconds.\n"
            )
        elapsed = time.perf_counter() - started
        (case_output / "stdout.txt").write_text(stdout, encoding="utf-8")
        (case_output / "stderr.txt").write_text(stderr, encoding="utf-8")
        report = _read_json(case_output / "report.json")
        geometry = _geometry_metrics(case_output)
        cases.append({
            "name": f"{group}/{case_name}",
            "block": block,
            "input": str(source),
            "status": report.get("status", "timeout" if returncode == 124 else "error"),
            "returncode": returncode,
            "elapsed_seconds": round(elapsed, 4),
            "warnings": report.get("warnings", []),
            "error": report.get("error"),
            "latex": report.get("latex", {}),
            "document_import": report.get("document_import", {}),
            "geometry": geometry,
            "artifacts": {
                "report": _existing(case_output / "report.json"),
                "preview": _existing(case_output / "plotter-preview.svg"),
                "gcode": _existing(case_output / "output.gcode"),
            },
        })

    summary = {
        "base_commit": _git_head(),
        "font": str(font),
        "fixture_count": len(cases),
        "successful": sum(case["status"] == "ok" for case in cases),
        "failed_or_unsupported": sum(case["status"] != "ok" for case in cases),
        "known_baseline_limitations": [
            "LaTeX formulas use segment_types=latex-outline",
            "PDF LaTeX mode is disabled and source LaTeX is not reconstructed",
            "OMML emits omml_equation_not_supported",
            "reflow does not use image source bbox and centers images",
            "text does not flow around image exclusion zones",
            "DOCX underline styling is lost",
            "DOCX tables are flattened into ordinary text",
            "filled PDF arrowheads can be rasterized",
            "PDF lines have no semantic classification",
        ],
        "cases": cases,
    }
    (output_root / "baseline-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Baseline complete: {summary['successful']}/{summary['fixture_count']} successful; "
        f"summary={output_root / 'baseline-summary.json'}"
    )
    return 0


def _geometry_metrics(output: Path) -> dict[str, object]:
    paths_files = [output / "paths.json", *sorted((output / "pages").glob("page-*/paths.json"))]
    strokes: list[dict[str, object]] = []
    for path in paths_files:
        payload = _read_json(path)
        raw_strokes = payload.get("strokes", [])
        if isinstance(raw_strokes, list):
            strokes.extend(item for item in raw_strokes if isinstance(item, dict))
    latex = [stroke for stroke in strokes if stroke.get("element_type") == "latex"]
    return {
        "strokes": len(strokes),
        "points": sum(len(stroke.get("points", [])) for stroke in strokes),
        "latex_strokes": len(latex),
        "latex_pen_lifts": len(latex),
        "latex_points": sum(len(stroke.get("points", [])) for stroke in latex),
        "latex_draw_length_mm": round(sum(_stroke_length(stroke) for stroke in latex), 6),
        "latex_outline_strokes": sum(
            "latex-outline" in stroke.get("segment_types", []) for stroke in latex
        ),
    }


def _stroke_length(stroke: dict[str, object]) -> float:
    points = stroke.get("points", [])
    if not isinstance(points, list):
        return 0.0
    result = 0.0
    previous: tuple[float, float] | None = None
    first: tuple[float, float] | None = None
    for point in points:
        if isinstance(point, dict):
            current = (float(point.get("x", 0.0)), float(point.get("y", 0.0)))
        elif isinstance(point, list) and len(point) >= 2:
            current = (float(point[0]), float(point[1]))
        else:
            continue
        first = first or current
        if previous is not None:
            result += math.dist(previous, current)
        previous = current
    if stroke.get("closed") and previous is not None and first is not None:
        result += math.dist(previous, first)
    return result


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _existing(path: Path) -> str | None:
    return str(path) if path.is_file() else None


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or "unknown"


def _refresh_geometry(output_root: Path) -> None:
    summary_path = output_root / "baseline-summary.json"
    summary = _read_json(summary_path)
    cases = summary.get("cases")
    if not isinstance(cases, list):
        raise TypeError(f"No baseline cases found in {summary_path}")
    for case in cases:
        if not isinstance(case, dict):
            continue
        name = str(case.get("name", ""))
        block = str(case.get("block", ""))
        case_name = name.split("/", 1)[-1]
        case["geometry"] = _geometry_metrics(output_root / block / case_name)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Refreshed geometry metrics in {summary_path}")


if __name__ == "__main__":
    raise SystemExit(main())
