"""Manual cold/warm conversion benchmark; intentionally not collected by pytest."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from plotter_processor.pipeline import PipelineOptions, run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3, help="Number of warm runs")
    parser.add_argument("--output", type=Path, default=Path("build/benchmark-conversion.json"))
    parser.add_argument("--page", choices=("A4", "A5"), default="A5")
    parser.add_argument("--size", choices=("small", "normal", "large"), default="normal")
    parser.add_argument("--font-mode", choices=("outline", "centerline"), default="centerline")
    parser.add_argument(
        "--document-layout", choices=("reflow", "hybrid", "preserve"), default="hybrid"
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    runs_root = args.output.parent / f"{args.output.stem}-runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="plotter-benchmark-") as temporary:
        cache_path = Path(temporary) / "centerlines.json"
        for index in range(args.runs + 1):
            output_dir = runs_root / f"run-{index:03d}"
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
            )
            started = time.perf_counter()
            result = run_pipeline(options)
            wall_ms = (time.perf_counter() - started) * 1000.0
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            if result.status != "ok":
                raise RuntimeError(f"Benchmark run {index} failed: {result.error}")
            results.append({
                "kind": "cold" if index == 0 else "warm",
                "wall_ms": round(wall_ms, 3),
                "performance": report.get("performance", {}),
                "cache": report.get("cache", {}),
                "statistics": report.get("statistics", {}),
                "output_dir": str(output_dir),
            })

    warm_values = [float(item["wall_ms"]) for item in results[1:]]
    payload = {
        "input": str(args.input),
        "font": str(args.font),
        "page": args.page,
        "size": args.size,
        "font_mode": args.font_mode,
        "document_layout": args.document_layout,
        "cold_ms": results[0]["wall_ms"],
        "warm_median_ms": round(statistics.median(warm_values), 3),
        "warm_runs": args.runs,
        "runs": results,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
