"""Manual cold/warm conversion benchmark; intentionally not collected by pytest."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

from plotter_processor.performance import FunctionProfiler
from plotter_processor.pipeline import PipelineOptions, run_pipeline


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gcode_is_safe(path: Path) -> bool:
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split(";", 1)[0].strip().upper()
        if not line:
            continue
        tokens = line.split()
        if tokens[0] in {"G28", "M104", "M109", "M140", "M190"}:
            return False
        for token in tokens[1:]:
            if "NAN" in token or "INF" in token:
                return False
            if token.startswith("E"):
                try:
                    float(token[1:])
                except ValueError:
                    continue
                return False
    return True


def _artifact_hashes(result: dict[str, object]) -> dict[str, str | None]:
    existing = result.get("artifacts_sha256")
    if isinstance(existing, dict):
        return {
            str(key): str(value) if value is not None else None
            for key, value in existing.items()
        }
    output_dir = Path(str(result.get("output_dir", "")))
    return {
        "paths": _file_sha256(output_dir / "paths.json"),
        "gcode": _file_sha256(output_dir / "output.gcode"),
    }


def _verification_summary(
    baseline: dict[str, object], current: dict[str, object]
) -> dict[str, object]:
    baseline_runs = baseline.get("runs", [])
    current_runs = current.get("runs", [])
    if not isinstance(baseline_runs, list) or not isinstance(current_runs, list):
        raise TypeError("Benchmark payload has invalid runs")
    baseline_artifacts = [
        _artifact_hashes(run) for run in baseline_runs if isinstance(run, dict)
    ]
    current_artifacts = [
        _artifact_hashes(run) for run in current_runs if isinstance(run, dict)
    ]
    baseline_reference = baseline_artifacts[-1] if baseline_artifacts else {}
    current_reference = current_artifacts[-1] if current_artifacts else {}
    current_paths = {item.get("paths") for item in current_artifacts}
    current_gcodes = {item.get("gcode") for item in current_artifacts}
    baseline_ms = baseline.get("warm_median_ms") or baseline.get("cold_ms")
    current_ms = current.get("warm_median_ms") or current.get("cold_ms")
    speedup = (
        float(baseline_ms) / float(current_ms)
        if isinstance(baseline_ms, (int, float))
        and isinstance(current_ms, (int, float))
        and current_ms
        else None
    )
    baseline_pages = {
        int(run.get("page_count", 1))
        for run in baseline_runs
        if isinstance(run, dict)
    }
    current_pages = {
        int(run.get("page_count", 1))
        for run in current_runs
        if isinstance(run, dict)
    }
    geometry_equal = (
        bool(baseline_reference.get("paths"))
        and baseline_reference.get("paths") == current_reference.get("paths")
    )
    gcode_equal = (
        bool(baseline_reference.get("gcode"))
        and baseline_reference.get("gcode") == current_reference.get("gcode")
    )
    return {
        "baseline_warm_median_ms": baseline.get("warm_median_ms"),
        "current_warm_median_ms": current.get("warm_median_ms"),
        "speedup": round(speedup, 3) if speedup is not None else None,
        "geometry_equal": geometry_equal,
        "gcode_equal": gcode_equal,
        "pages_equal": baseline_pages == current_pages,
        "deterministic_paths": len(current_paths) == 1 and None not in current_paths,
        "deterministic_gcode": len(current_gcodes) == 1 and None not in current_gcodes,
        "gcode_safety": all(
            run.get("gcode_safety") == "passed"
            for run in current_runs
            if isinstance(run, dict)
        ),
        "regression_free": geometry_equal
        and gcode_equal
        and baseline_pages == current_pages,
    }


def _run_timings(result: dict[str, object]) -> dict[str, float]:
    performance = result.get("performance", {})
    if not isinstance(performance, dict):
        return {}
    timings = {
        f"stage.{key}": float(value)
        for key, value in performance.items()
        if (key == "total_ms" or key.endswith("_ms"))
        and isinstance(value, (int, float))
    }
    pages = performance.get("pages", [])
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            hotspots = page.get("hotspots", {})
            if not isinstance(hotspots, dict):
                continue
            for name, metric in hotspots.items():
                if isinstance(metric, dict) and isinstance(
                    metric.get("total_ms"), (int, float)
                ):
                    key = f"hotspot.{name}"
                    timings[key] = timings.get(key, 0.0) + float(metric["total_ms"])
    return timings


def _performance_summary(results: list[dict[str, object]]) -> dict[str, object]:
    cold = [_run_timings(result) for result in results if result.get("kind") == "cold"]
    warm = [_run_timings(result) for result in results if result.get("kind") == "warm"]
    keys = sorted({key for timings in [*cold, *warm] for key in timings})
    return {
        "cold_ms": {
            key: round(cold[0][key], 3) for key in keys if cold and key in cold[0]
        },
        "warm_median_ms": {
            key: round(
                statistics.median(
                    timings[key] for timings in warm if key in timings
                ),
                3,
            )
            for key in keys
            if any(key in timings for timings in warm)
        },
    }


def _progress_reporter(label: str) -> Callable[[str, str, float | None], None]:
    def report(stage: str, state: str, elapsed_ms: float | None) -> None:
        suffix = "" if elapsed_ms is None else f" ({elapsed_ms:.1f} ms)"
        print(f"[benchmark] {label}: {stage} {state}{suffix}", flush=True)

    return report


def _combined_progress(
    *callbacks: Callable[[str, str, float | None], None],
) -> Callable[[str, str, float | None], None]:
    def report(stage: str, state: str, elapsed_ms: float | None) -> None:
        for callback in callbacks:
            callback(stage, state, elapsed_ms)

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--cold-only", action="store_true")
    modes.add_argument("--warm-only", action="store_true")
    parser.add_argument("--warm-runs", type=int, default=3, help="Number of warm runs")
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=2,
        help="Warmup runs excluded from the measured median",
    )
    parser.add_argument(
        "--runs",
        type=int,
        dest="warm_runs",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--output", type=Path, default=Path("build/benchmark-conversion.json"))
    parser.add_argument(
        "--baseline", type=Path, help="Compare against a previous benchmark JSON"
    )
    parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    parser.add_argument("--font-mode", choices=("outline", "centerline"), default="centerline")
    parser.add_argument(
        "--connections", choices=("off", "safe", "aggressive"), default="safe"
    )
    parser.add_argument("--workers", default="auto")
    parser.add_argument(
        "--artifacts", choices=("normal", "debug", "audit"), default="normal"
    )
    parser.add_argument(
        "--document-layout", choices=("reflow", "hybrid", "preserve"), default="hybrid"
    )
    profile_modes = parser.add_mutually_exclusive_group()
    profile_modes.add_argument(
        "--profile", action="store_true", help="Profile the complete conversion with cProfile"
    )
    profile_modes.add_argument(
        "--profile-stage",
        choices=FunctionProfiler.PROFILE_STAGES,
        help="Profile only calls belonging to one hot pipeline stage",
    )
    parser.add_argument(
        "--profile-top", type=int, default=20, help="Number of functions in the profile list"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print the complete per-run JSON payload"
    )
    args = parser.parse_args()
    if args.warm_runs < 1:
        parser.error("--warm-runs must be at least 1")
    if args.warmup_runs < 0:
        parser.error("--warmup-runs must be non-negative")
    if args.profile_top < 20:
        parser.error("--profile-top must be at least 20")
    benchmark_workers = 1 if args.profile or args.profile_stage else args.workers

    args.output.parent.mkdir(parents=True, exist_ok=True)
    runs_root = args.output.parent / f"{args.output.stem}-runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    temporary_context = (
        nullcontext(None)
        if args.warm_only
        else tempfile.TemporaryDirectory(prefix="plotter-benchmark-")
    )
    with temporary_context as temporary:
        cache_path = None if temporary is None else Path(temporary) / "centerlines.json"
        kinds = (
            ["cold"]
            if args.cold_only
            else ["warmup"] * args.warmup_runs + ["warm"] * args.warm_runs
            if args.warm_only
            else [
                "cold",
                *(["warmup"] * args.warmup_runs),
                *(["warm"] * args.warm_runs),
            ]
        )
        for index, kind in enumerate(kinds):
            output_dir = runs_root / f"run-{index:03d}"
            label = f"{kind} run {index + 1}/{len(kinds)}"
            profiler = (
                FunctionProfiler(args.profile_stage)
                if args.profile or args.profile_stage
                else None
            )
            progress = _progress_reporter(label)
            if profiler is not None:
                progress = _combined_progress(progress, profiler.progress)

            options = PipelineOptions(
                args.input,
                args.font,
                args.page,
                args.size,
                Path("configs/layout.yaml"),
                Path("configs/machine.yaml"),
                output_dir,
                font_mode=args.font_mode,
                centerline_cache_path=cache_path,
                document_layout=args.document_layout,
                layout_debug=False,
                connections=args.connections,
                latex="mathtext",
                latex_stroke_mode=args.font_mode,
                strict_latex_quality=args.font_mode == "centerline",
                page_numbers=True,
                stage_progress=progress,
                workers=benchmark_workers,
                artifact_level=args.artifacts,
            )
            print(f"[benchmark] {label}: conversion started", flush=True)
            started = time.perf_counter()
            if profiler is not None:
                profiler.start()
            try:
                result = run_pipeline(options)
            finally:
                if profiler is not None:
                    profiler.stop()
            wall_ms = (time.perf_counter() - started) * 1000.0
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            if result.status != "ok":
                raise RuntimeError(f"Benchmark run {index} failed: {result.error}")
            print(
                f"[benchmark] {label}: conversion completed ({wall_ms:.1f} ms)",
                flush=True,
            )
            run_result: dict[str, object] = {
                "kind": kind,
                "wall_ms": round(wall_ms, 3),
                "performance": report.get("performance", {}),
                "cache": report.get("cache", {}),
                "statistics": report.get("statistics", {}),
                "output_dir": str(output_dir),
                "page_count": int(report.get("pagination", {}).get("page_count", 1)),
                "gcode_safety": (
                    "passed"
                    if _gcode_is_safe(output_dir / "output.gcode")
                    else "failed"
                ),
                "artifacts_sha256": {
                    "paths": _file_sha256(output_dir / "paths.json"),
                    "gcode": _file_sha256(output_dir / "output.gcode"),
                },
            }
            if profiler is not None:
                profile_path = args.output.parent / (
                    f"{args.output.stem}-run-{index:03d}.prof"
                )
                profiler.dump(profile_path)
                run_result["profile"] = {
                    "stage": args.profile_stage or "complete",
                    "stats_path": str(profile_path),
                    "top_functions": profiler.top_functions(args.profile_top),
                }
            results.append(run_result)

    cold_values = [float(item["wall_ms"]) for item in results if item["kind"] == "cold"]
    warm_values = [float(item["wall_ms"]) for item in results if item["kind"] == "warm"]
    payload = {
        "input": str(args.input),
        "font": str(args.font),
        "page": args.page,
        "size": args.size,
        "font_mode": args.font_mode,
        "connections": args.connections,
        "workers": benchmark_workers,
        "artifacts": args.artifacts,
        "document_layout": args.document_layout,
        "mode": (
            "cold-only"
            if args.cold_only
            else "warm-only"
            if args.warm_only
            else "cold+warm"
        ),
        "cold_ms": cold_values[0] if cold_values else None,
        "warm_median_ms": round(statistics.median(warm_values), 3) if warm_values else None,
        "warm_runs": len(warm_values),
        "warmup_runs": sum(item["kind"] == "warmup" for item in results),
        "performance_summary": _performance_summary(results),
        "runs": results,
    }
    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError("Baseline benchmark must contain a JSON object")
        payload["baseline"] = str(args.baseline)
        payload["verification"] = _verification_summary(baseline, payload)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    console_payload = payload if args.verbose else {
        "cold_ms": payload["cold_ms"],
        "warm_median_ms": payload["warm_median_ms"],
        "warm_runs": payload["warm_runs"],
        "warmup_runs": payload["warmup_runs"],
        "performance_summary": payload["performance_summary"],
        **({"verification": payload["verification"]} if "verification" in payload else {}),
        "output": str(args.output),
    }
    print(json.dumps(console_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
