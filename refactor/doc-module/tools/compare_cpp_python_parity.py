#!/usr/bin/env python3
"""Run bounded native-vs-frozen-Python parity checks and optional timings.

The Python golden corpus is the reference.  The native CLI writes a different
artifact schema, so this intentionally compares only stable, cross-schema
facts: pages, glyph totals, strokes and bounds, stroke provenance, and a
conservative G-code safety scan.  A missing field is reported as ``unavailable``
instead of being treated as equal.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

MODULE = Path(__file__).resolve().parents[1]
ROOT = MODULE.parents[1]
CORPUS = MODULE / "golden" / "corpus.json"
CPP_TIMING_FIELDS = ("import_ms", "layout_ms", "path_and_geometry_ms", "gcode_ms", "peak_rss_kib")


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp", type=Path, help="path to plotter-doc (auto-detected when omitted)")
    parser.add_argument("--python", dest="python_executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--case", dest="cases", action="append", help="case id; may be repeated")
    parser.add_argument("--output", type=Path, default=Path("/tmp/cppdoc-parity"))
    parser.add_argument("--font", type=Path, default=ROOT / "assets" / "1.ttf")
    parser.add_argument("--runs", type=int, default=1, help="timed runs per implementation (default: 1)")
    parser.add_argument("--benchmark", action="store_true", help="also time full isolated pipeline runs")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--tolerance-mm", type=float, default=0.01)
    return parser.parse_args()


def native_executable(requested: Path | None) -> Path | None:
    if requested:
        return requested.resolve() if requested.is_file() else None
    names = ("plotter-doc", "plotter_doc_cli")
    for base in (ROOT / "build", MODULE / "build"):
        if base.exists():
            for name in names:
                found = list(base.rglob(name))
                if found:
                    return found[0]
    return None


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_key(value: Any, key: str) -> Iterable[Any]:
    if isinstance(value, dict):
        if key in value:
            yield value[key]
        for item in value.values():
            yield from find_key(item, key)
    elif isinstance(value, list):
        for item in value:
            yield from find_key(item, key)


def as_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def point_xy(point: Any) -> tuple[float, float] | None:
    if isinstance(point, dict):
        x, y = as_number(point.get("x")), as_number(point.get("y"))
        if x is not None and y is not None:
            return x, y
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        x, y = as_number(point[0]), as_number(point[1])
        if x is not None and y is not None:
            return x, y
    return None


def strokes_from(paths: dict[str, Any]) -> list[dict[str, Any]]:
    value = paths.get("value", paths.get("paths", paths))
    return value.get("strokes", []) if isinstance(value, dict) else []


def bbox(stroke: dict[str, Any]) -> tuple[float, float, float, float] | None:
    points = [point_xy(point) for point in stroke.get("points", [])]
    points = [point for point in points if point is not None]
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def bbox_signature(strokes: list[dict[str, Any]]) -> Counter[tuple[float, float, float, float]]:
    return Counter(tuple(round(value, 3) for value in box) for stroke in strokes if (box := bbox(stroke)) is not None)


def provenance(strokes: list[dict[str, Any]]) -> Counter[tuple[Any, ...]]:
    fields = ("element_id", "element_type", "source_page_index", "semantic_role", "source_path", "glyph_index", "character")
    return Counter(tuple(stroke.get(field) for field in fields) for stroke in strokes)


def golden_paths(case_id: str) -> list[dict[str, Any]]:
    directory = MODULE / "golden" / case_id / "paths"
    return [load(path) for path in sorted(directory.glob("*.json"))]


def native_paths(directory: Path) -> list[dict[str, Any]]:
    return [load(path) for path in sorted(directory.glob("pages/page-*/paths.json"))]


def metric(name: str, expected: Any, actual: Any, *, available: bool = True) -> dict[str, Any]:
    def display(value: Any) -> Any:
        if isinstance(value, Counter):
            return {repr(key): count for key, count in sorted(value.items(), key=lambda item: repr(item[0]))}
        return value
    status = "pass" if available and expected == actual else ("fail" if available else "unavailable")
    result = {"name": name, "status": status}
    if isinstance(expected, Counter) and isinstance(actual, Counter):
        expected_only = expected - actual
        actual_only = actual - expected
        result.update({
            "expected_total": sum(expected.values()), "actual_total": sum(actual.values()),
            "expected_only": display(Counter(dict(expected_only.most_common(12)))),
            "actual_only": display(Counter(dict(actual_only.most_common(12)))),
            "expected_only_total": sum(expected_only.values()),
            "actual_only_total": sum(actual_only.values()),
        })
    else:
        result.update({"expected": display(expected), "actual": display(actual)})
    return result


def gcode_safety(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "unavailable", "reason": "output.gcode was not produced"}
    pen: str | None = None
    errors: list[str] = []
    commands = 0
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("("):
            continue
        tokens = line.split()
        command = tokens[0].upper()
        if command not in {"G0", "G00", "G1", "G01", "G21", "G90", "G28", "M400", "M84", "G4"}:
            errors.append(f"line {number}: unsupported command {command}")
            continue
        commands += 1
        values: dict[str, float] = {}
        for token in tokens[1:]:
            if len(token) > 1 and token[0].upper() in "XYZFSP":
                try:
                    values[token[0].upper()] = float(token[1:])
                except ValueError:
                    errors.append(f"line {number}: invalid parameter {token}")
        if "Z" in values:
            pen = "up" if command in {"G0", "G00"} else "down" if command in {"G1", "G01"} else pen
        if ("X" in values or "Y" in values) and pen is None:
            errors.append(f"line {number}: XY motion before a pen state")
        if ("X" in values or "Y" in values) and command in {"G0", "G00"} and pen != "up":
            errors.append(f"line {number}: rapid XY motion with pen not raised")
        if ("X" in values or "Y" in values) and command in {"G1", "G01"} and pen != "down":
            errors.append(f"line {number}: draw XY motion with pen not lowered")
    return {"status": "pass" if not errors else "fail", "commands": commands, "errors": errors[:20]}


def run(command: list[str], cwd: Path) -> tuple[int, float, str]:
    started = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=120)
    return result.returncode, time.perf_counter() - started, (result.stdout + result.stderr)[-4000:]


def python_command(case: dict[str, Any], output: Path, python_executable: Path, font: Path) -> list[str]:
    command = [str(python_executable), str(MODULE / "tools" / "capture_python_pipeline.py"), str(ROOT / case["input"]), "--output", str(output), "--font", str(font), "--page", case["page"], "--font-mode", case["font_mode"], "--workers", "1"]
    if machine := case.get("machine_config"):
        command.extend(("--machine-config", str(ROOT / machine)))
    return command


def cpp_command(case: dict[str, Any], output: Path, executable: Path, font: Path, cache_dir: Path | None = None) -> list[str]:
    command = [str(executable), "--input", str(ROOT / case["input"]), "--output", str(output), "--font", str(font), "--page", case["page"], "--font-mode", case["font_mode"], "--layout-config", str(ROOT / "configs/layout.yaml"), "--artifact-level", "normal"]
    # The frozen corpus predates an explicit field and includes page numbers.
    # New cases can opt out without changing the command-line harness.
    if case.get("page_numbers", True):
        command.append("--page-numbers")
    if cache_dir is not None:
        command.extend(("--cache-dir", str(cache_dir)))
    if machine := case.get("machine_config"):
        command.extend(("--machine-config", str(ROOT / machine)))
    return command


def unavailable(reason: str) -> dict[str, str]:
    return {"status": "unavailable", "reason": reason}


def native_benchmark_sample(output: Path, wall_seconds: float, cache_state: str) -> dict[str, Any]:
    """Read metrics emitted by a single native process without guessing values."""
    report_path = output / "report.json"
    native_report = load(report_path).get("report", {}) if report_path.is_file() else {}
    timings = native_report.get("timings", {})
    stage_timings: dict[str, Any] = {}
    for field in CPP_TIMING_FIELDS:
        value = timings.get(field)
        stage_timings[field] = round(value, 6) if isinstance(value, (int, float)) else unavailable("native report did not expose this field")
    cache = native_report.get("cache", {})
    cache_metrics = {
        field: cache[field] if isinstance(cache.get(field), int) else unavailable("native report did not expose this field")
        for field in ("hits", "misses")
    }
    return {
        "cache_state": cache_state,
        "wall_seconds": round(wall_seconds, 6),
        "stage_timings": stage_timings,
        "cache": cache_metrics,
    }


def python_benchmark_sample(wall_seconds: float) -> dict[str, Any]:
    reason = "Python capture does not emit stage timings or peak RSS in this harness"
    return {
        "wall_seconds": round(wall_seconds, 6),
        "stage_timings": {field: unavailable(reason) for field in CPP_TIMING_FIELDS},
        "cache": unavailable("Python cache statistics are not comparable to native StageCache"),
    }


def compare(case: dict[str, Any], cpp_dir: Path, tolerance: float) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    native_job_path = cpp_dir / "job.json"
    if not native_job_path.is_file():
        return {"case": case["id"], "status": "error", "checks": [], "error": "native job.json is missing"}
    native_job = load(native_job_path).get("job", {})
    frozen_job = load(MODULE / "golden" / case["id"] / "job.json").get("job", {})
    checks.append(metric("page_count", frozen_job.get("page_count"), native_job.get("page_count")))
    frozen_strokes = [stroke for page in golden_paths(case["id"]) for stroke in strokes_from(page)]
    cpp_strokes = [stroke for page in native_paths(cpp_dir) for stroke in strokes_from(page)]
    checks.append(metric("stroke_count", len(frozen_strokes), len(cpp_strokes)))
    checks.append(metric("stroke_bounding_boxes", bbox_signature(frozen_strokes), bbox_signature(cpp_strokes)))
    has_frozen_provenance = any(any(value is not None for value in item) for item in provenance(frozen_strokes))
    has_cpp_provenance = any(any(value is not None for value in item) for item in provenance(cpp_strokes))
    checks.append(metric("stroke_provenance", provenance(frozen_strokes), provenance(cpp_strokes), available=has_frozen_provenance and has_cpp_provenance))
    frozen_report = load(MODULE / "golden" / case["id"] / "report.json").get("report", {})
    cpp_report_path = cpp_dir / "report.json"
    cpp_report = load(cpp_report_path).get("report", {}) if cpp_report_path.is_file() else {}
    frozen_glyphs = frozen_report.get("statistics", {}).get("glyphs")
    cpp_glyphs = cpp_report.get("layout", {}).get("glyphs")
    checks.append(metric("glyph_count", frozen_glyphs, cpp_glyphs, available=frozen_glyphs is not None and cpp_glyphs is not None))
    safety = gcode_safety(cpp_dir / "output.gcode")
    checks.append({"name": "gcode_safety", **safety})
    failures = [check["name"] for check in checks if check["status"] in {"fail", "error"}]
    return {"case": case["id"], "status": "pass" if not failures else "fail", "checks": checks, "mismatches": failures, "tolerance_mm": tolerance}


def main() -> int:
    options = args()
    if options.runs < 1:
        raise SystemExit("--runs must be at least 1")
    executable = native_executable(options.cpp)
    if executable is None:
        raise SystemExit("native plotter-doc not found; pass --cpp /path/to/plotter-doc")
    corpus = load(CORPUS)["cases"]
    selected = [case for case in corpus if case.get("golden") and (not options.cases or case["id"] in options.cases)]
    missing = set(options.cases or ()) - {case["id"] for case in selected}
    if missing:
        raise SystemExit("unknown or non-frozen case(s): " + ", ".join(sorted(missing)))
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"format": "cppdoc-parity-report", "native": str(executable), "python": str(options.python_executable), "cases": [], "benchmarks": []}
    for case in selected:
        case_dir = output / case["id"]
        shutil.rmtree(case_dir, ignore_errors=True)
        cpp_dir = case_dir / "cpp"
        cache_dir = case_dir / "cpp-cache" if options.benchmark else None
        code, seconds, text = run(cpp_command(case, cpp_dir, executable, options.font.resolve(), cache_dir), ROOT)
        if code:
            result = {"case": case["id"], "status": "error", "checks": [], "native_exit": code, "native_output": text}
        else:
            result = compare(case, cpp_dir, options.tolerance_mm)
            result["native_seconds"] = round(seconds, 6)
        report["cases"].append(result)
        if options.benchmark and code == 0:
            timings: dict[str, list[float]] = {"cpp": [seconds], "python": []}
            cpp_samples = [native_benchmark_sample(cpp_dir, seconds, "cold")]
            for iteration in range(1, options.runs):
                target = case_dir / "timing" / "cpp" / str(iteration)
                timing_code, elapsed, _ = run(cpp_command(case, target, executable, options.font.resolve(), cache_dir), ROOT)
                if timing_code == 0:
                    timings["cpp"].append(elapsed)
                    cpp_samples.append(native_benchmark_sample(target, elapsed, "warm"))
            python_samples = []
            for iteration in range(options.runs):
                target = case_dir / "timing" / "python" / str(iteration)
                timing_code, elapsed, _ = run(python_command(case, target, options.python_executable, options.font.resolve()), ROOT)
                if timing_code == 0:
                    timings["python"].append(elapsed)
                    python_samples.append(python_benchmark_sample(elapsed))
            if len(timings["cpp"]) == options.runs and len(timings["python"]) == options.runs:
                warm = cpp_samples[1:]
                report["benchmarks"].append({
                    "case": case["id"], "runs": options.runs,
                    "cpp_seconds": [round(value, 6) for value in timings["cpp"]],
                    "python_seconds": [round(value, 6) for value in timings["python"]],
                    "cpp_median_seconds": round(sorted(timings["cpp"])[len(timings["cpp"]) // 2], 6),
                    "python_median_seconds": round(sorted(timings["python"])[len(timings["python"]) // 2], 6),
                    "cpp_cold_cache": cpp_samples[0],
                    "cpp_warm_cache": warm if warm else unavailable("--runs 1 creates no warm-cache sample"),
                    "python": python_samples,
                })
    report_path = output / "parity-report.json"
    report_path.write_text(json.dumps(report, indent=2, default=lambda value: dict(value) if isinstance(value, Counter) else str(value)) + "\n", encoding="utf-8")
    print(report_path)
    if not options.keep_artifacts:
        for case in selected:
            shutil.rmtree(output / case["id"] / "timing", ignore_errors=True)
    return 0 if all(item["status"] == "pass" for item in report["cases"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
