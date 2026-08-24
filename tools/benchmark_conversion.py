"""Manual cold/warm conversion benchmark; intentionally not collected by pytest."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

from plotter_processor.performance import FunctionProfiler
from plotter_processor.pipeline import PipelineOptions, run_pipeline


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
        "--runs",
        type=int,
        dest="warm_runs",
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--output", type=Path, default=Path("build/benchmark-conversion.json"))
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
    args = parser.parse_args()
    if args.warm_runs < 1:
        parser.error("--warm-runs must be at least 1")
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
            else ["warm"] * args.warm_runs
            if args.warm_only
            else ["cold", *(["warm"] * args.warm_runs)]
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
        "runs": results,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
