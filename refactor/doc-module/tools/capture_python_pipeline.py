#!/usr/bin/env python3
"""Capture and compare frozen outputs from the current Python document pipeline."""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from canonical_serializers import (  # noqa: E402
    canonical_document,
    canonical_job,
    canonical_layout,
    canonical_paths,
    canonical_report,
    write_canonical_json,
)
import plotter_processor.pipeline as python_pipeline  # noqa: E402
from plotter_processor.pipeline import PipelineOptions, run_pipeline  # noqa: E402
from plotter_processor.structured_document_reader import read_structured_document  # noqa: E402


STAGES = ("document", "layout", "paths", "job", "report", "gcode", "preview")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="snapshot directory")
    parser.add_argument("--golden", type=Path, help="compare snapshots against this directory")
    parser.add_argument("--update-golden", action="store_true")
    parser.add_argument("--font", type=Path, default=REPO_ROOT / "assets/1.ttf")
    parser.add_argument("--layout-config", type=Path, default=REPO_ROOT / "configs/layout.yaml")
    parser.add_argument("--machine-config", type=Path, default=REPO_ROOT / "configs/machine.yaml")
    parser.add_argument("--page", default="A5")
    parser.add_argument("--size", default="normal")
    parser.add_argument("--font-mode", choices=("outline", "centerline"), default="outline")
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_dir = args.output.resolve()
    raw_dir = snapshot_dir / ".python-output"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    roots = {
        REPO_ROOT.resolve(): "<repo>",
        args.input.resolve(): "<input>",
        args.font.resolve(): "<font>",
        raw_dir.resolve(): "<run>",
    }

    document_models: list[object] = []
    original_read = python_pipeline.read_structured_document
    original_paginate = python_pipeline.paginate_document
    layout_models: list[object] = []

    def capture_document(*values: object, **kwargs: object) -> object:
        model = original_read(*values, **kwargs)
        document_models.append(model)
        return model

    def capture_layout(*values: object, **kwargs: object) -> object:
        model = original_paginate(*values, **kwargs)
        layout_models.append(model)
        return model

    python_pipeline.read_structured_document = capture_document
    python_pipeline.paginate_document = capture_layout
    try:
        result = run_pipeline(PipelineOptions(
        input_path=args.input,
        font_path=args.font,
        page=args.page,
        size=args.size,
        layout_config_path=args.layout_config,
        machine_config_path=args.machine_config,
        output_dir=raw_dir,
        font_mode=args.font_mode,
        workers=args.workers,
        artifact_level="normal",
        layout_debug=True,
        semantic_debug=True,
        stage_cache_path=raw_dir / ".stage-cache",
        ))
    finally:
        python_pipeline.read_structured_document = original_read
        python_pipeline.paginate_document = original_paginate
    if result.status != "ok":
        print(f"Python pipeline failed: {result.error}", file=sys.stderr)
        return 1

    if len(document_models) != 1:
        print("Python pipeline did not execute exactly one document stage; use an empty stage cache", file=sys.stderr)
        return 1
    write_canonical_json(snapshot_dir / "document.json", canonical_document(document_models[0], roots=roots), roots=roots)
    if len(layout_models) != 1:
        print("Python pipeline did not execute exactly one layout stage; use an empty stage cache", file=sys.stderr)
        return 1
    report = _load(raw_dir / "report.json")
    write_canonical_json(
        snapshot_dir / "layout.json",
        canonical_layout(layout_models[0], _load(raw_dir / "layout-debug/placement.json"), _load(raw_dir / "layout-debug/trace.json"), report, roots=roots),
        roots=roots,
    )
    write_canonical_json(snapshot_dir / "report.json", canonical_report(report, roots=roots), roots=roots)
    job = _load(raw_dir / "job.json")
    write_canonical_json(snapshot_dir / "job.json", canonical_job(job, roots=roots), roots=roots)
    for page in job["pages"]:
        source = raw_dir / page["paths"]
        target = snapshot_dir / "paths" / f"page-{int(page['page_number']):03d}.json"
        write_canonical_json(target, canonical_paths(_load(source), roots=roots), roots=roots)
    _copy_gcode(raw_dir, job, snapshot_dir)
    _copy_preview(raw_dir, snapshot_dir)
    _write_manifest(snapshot_dir)

    if args.update_golden:
        if args.golden is None:
            raise SystemExit("--update-golden requires --golden")
        _replace_golden(snapshot_dir, args.golden.resolve())
    if args.golden is not None:
        return _compare(snapshot_dir, args.golden.resolve())
    print(f"Captured canonical stages in {snapshot_dir}")
    return 0


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_gcode(raw_dir: Path, job: dict[str, object], snapshot_dir: Path) -> None:
    for page in job["pages"]:
        source = raw_dir / str(page["gcode"])
        target = snapshot_dir / "gcode" / f"page-{int(page['page_number']):03d}.gcode"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8").replace("\r\n", "\n"), encoding="utf-8")
    combined = raw_dir / "output.gcode"
    if combined.exists():
        (snapshot_dir / "output.gcode").write_text(combined.read_text(encoding="utf-8").replace("\r\n", "\n"), encoding="utf-8")


def _copy_preview(raw_dir: Path, snapshot_dir: Path) -> None:
    source = raw_dir / "plotter-preview.svg"
    target = snapshot_dir / "preview.svg"
    target.write_text(source.read_text(encoding="utf-8").replace("\r\n", "\n"), encoding="utf-8")


def _write_manifest(snapshot_dir: Path) -> None:
    roots = ("document.json", "layout.json", "job.json", "report.json", "output.gcode", "preview.svg")
    files = [name for name in roots if (snapshot_dir / name).is_file()]
    for directory in ("paths", "gcode"):
        base = snapshot_dir / directory
        files.extend(path.relative_to(snapshot_dir).as_posix() for path in sorted(base.rglob("*")) if path.is_file())
    (snapshot_dir / "manifest.json").write_text(json.dumps({"format": "cppdoc-parity", "stages": list(STAGES), "files": files}, indent=2) + "\n", encoding="utf-8")


def _replace_golden(snapshot_dir: Path, golden_dir: Path) -> None:
    golden_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load(snapshot_dir / "manifest.json")
    previous = _load(golden_dir / "manifest.json") if (golden_dir / "manifest.json").exists() else {"files": []}
    for relative in previous.get("files", []):
        if relative not in manifest["files"]:
            (golden_dir / relative).unlink(missing_ok=True)
    for relative in manifest["files"]:
        source = snapshot_dir / relative
        target = golden_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(snapshot_dir / "manifest.json", golden_dir / "manifest.json")


def _compare(snapshot_dir: Path, golden_dir: Path) -> int:
    mismatches = []
    manifest = _load(snapshot_dir / "manifest.json")
    expected_manifest_path = golden_dir / "manifest.json"
    if not expected_manifest_path.exists() or manifest != _load(expected_manifest_path):
        mismatches.append("manifest.json")
    for relative in manifest["files"]:
        actual, expected = snapshot_dir / relative, golden_dir / relative
        if not expected.exists() or not filecmp.cmp(actual, expected, shallow=False):
            mismatches.append(relative)
    if mismatches:
        print("Parity mismatch: " + ", ".join(mismatches), file=sys.stderr)
        return 2
    print(f"Parity OK: {golden_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
