from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the UPD 7 block 2 examples.")
    parser.add_argument("--font", type=Path, default=Path("assets/1.ttf"))
    parser.add_argument("--examples", type=Path, default=Path("examples/update_7/block_2"))
    parser.add_argument(
        "--output-root", type=Path, default=Path("build/update_7/candidate/block_2")
    )
    args = parser.parse_args()
    font = args.font.resolve()
    examples = args.examples.resolve()
    output_root = args.output_root.resolve()
    if not font.is_file():
        raise FileNotFoundError(f"Font not found: {font}")
    subprocess.run(
        [sys.executable, "tools/generate_update_7_fixtures.py", "--block-2-examples-output", str(examples)],
        check=True,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")
    shared = [
        sys.executable, "-m", "plotter_processor", "run",
        "--font", str(font), "--font-mode", "centerline",
        "--centerline-cache", str(output_root / "shared-font-cache.json"),
        "--images", "centerline", "--connections", "safe", "--layout-debug",
        "--no-page-numbers", "--pdf-math", "off", "--page", "A5",
    ]
    jobs = [
        ("docx-left-hybrid", examples / "image-left-square-wrap.docx", "hybrid"),
        ("docx-right-hybrid", examples / "image-right-square-wrap.docx", "hybrid"),
        ("pdf-right-reflow", examples / "pdf-image-right.pdf", "reflow"),
        ("pdf-right-preserve", examples / "pdf-image-right.pdf", "preserve"),
    ]
    results: list[dict[str, object]] = []
    for name, source, layout_mode in jobs:
        output = output_root / name
        command = [
            *shared, str(source), "--document-layout", layout_mode,
            "--output-dir", str(output),
        ]
        print(f"Running {name}...", flush=True)
        completed = subprocess.run(
            command, check=False, capture_output=True, text=True, env=environment
        )
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (output / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        report = _read_json(output / "report.json")
        layout = report.get("document_layout", {})
        elements = layout.get("elements", []) if isinstance(layout, dict) else []
        first = elements[0] if elements else {}
        bbox = first.get("output_bbox_mm", {}) if isinstance(first, dict) else {}
        center_x = (
            float(bbox.get("x", 0.0)) + float(bbox.get("width", 0.0)) / 2
            if isinstance(bbox, dict) else None
        )
        results.append({
            "name": name, "input": str(source), "output": str(output),
            "returncode": completed.returncode, "status": report.get("status", "error"),
            "layout_mode": layout_mode, "center_x_mm": center_x,
            "mean_center_displacement_mm": layout.get("mean_center_displacement_mm"),
            "mean_scale_factor": layout.get("mean_scale_factor"),
            "overlaps_remaining": layout.get("overlaps_remaining"),
            "page_overflow_area_mm2": layout.get("page_overflow_area_mm2"),
            "unsafe_gcode_tokens": _unsafe_gcode_tokens(output / "output.gcode"),
            "artifacts": {
                "preview": _existing(output / "plotter-preview.svg"),
                "overlay": _existing(output / "layout-debug" / "placement-overlay.svg"),
                "placement": _existing(output / "layout-debug" / "placement.json"),
                "paths": _existing(output / "paths.json"),
                "report": _existing(output / "report.json"),
                "gcode": _existing(output / "output.gcode"),
            },
        })
    by_name = {item["name"]: item for item in results}
    success = all(
        item["returncode"] == 0 and item["status"] == "ok"
        and item["overlaps_remaining"] == 0 and item["page_overflow_area_mm2"] == 0
        and not item["unsafe_gcode_tokens"] for item in results
    )
    success = success and (
        float(by_name["docx-left-hybrid"]["center_x_mm"]) < 74
        and float(by_name["docx-right-hybrid"]["center_x_mm"]) > 74
        and abs(float(by_name["pdf-right-reflow"]["center_x_mm"]) - 74) < 0.001
        and float(by_name["pdf-right-preserve"]["center_x_mm"]) > 74
        and float(by_name["pdf-right-preserve"]["mean_center_displacement_mm"]) <= 1
    )
    summary = {"status": "ok" if success else "failed", "jobs": results}
    summary_path = output_root / "demo-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Demo {summary['status']}: {summary_path}")
    return 0 if success else 1


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _unsafe_gcode_tokens(path: Path) -> list[str]:
    if not path.is_file():
        return ["missing-output.gcode"]
    findings: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        tokens = raw_line.split(";", 1)[0].strip().upper().split()
        if not tokens:
            continue
        if tokens[0] in {"G28", "M104", "M109", "M140", "M190"}:
            findings.add(tokens[0])
        for token in tokens[1:]:
            if token.startswith("E") and _is_number(token[1:]):
                findings.add("extrusion")
            if "NAN" in token or "INF" in token:
                findings.add("non-finite")
    return sorted(findings)


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _existing(path: Path) -> str | None:
    return str(path) if path.is_file() else None


if __name__ == "__main__":
    raise SystemExit(main())
