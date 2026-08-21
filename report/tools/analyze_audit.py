"""Audit-only aggregation and independent safety checks."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def gcode_audit(path: Path, machine: dict) -> dict:
    text = path.read_text(encoding="utf-8")
    forbidden = [item for item in ("M104", "M109", "M140", "M190", "G28") if re.search(
        rf"(?m)^\s*{item}(?:\s|$)", text
    )]
    extrusion = len(re.findall(r"(?m)^\s*G(?:0|1)\b[^;\n]*\bE[-+]?\d", text))
    nonfinite = len(re.findall(r"(?i)(?:nan|infinity|\binf\b)", text))
    workspace = machine["workspace_mm"]
    xy_out = []
    z_values = []
    for line_number, line in enumerate(text.splitlines(), 1):
        code = line.split(";", 1)[0]
        if not re.match(r"\s*G(?:0|1)\b", code):
            continue
        x_match = re.search(r"(?:^|\s)X([-+]?\d+(?:\.\d+)?)", code)
        y_match = re.search(r"(?:^|\s)Y([-+]?\d+(?:\.\d+)?)", code)
        z_match = re.search(r"(?:^|\s)Z([-+]?\d+(?:\.\d+)?)", code)
        if x_match and y_match:
            x, y = float(x_match.group(1)), float(y_match.group(1))
            if not (
                workspace["min_x"] <= x <= workspace["max_x"]
                and workspace["min_y"] <= y <= workspace["max_y"]
            ):
                xy_out.append({"line": line_number, "x": x, "y": y})
        if z_match:
            z_values.append(float(z_match.group(1)))
    pen = machine["pen"]
    allowed_z = {float(pen["up_z_mm"]), float(pen["down_z_mm"])}
    for profile in machine.get("motion_profiles", {}).get("profiles", {}).values():
        allowed_z.update(
            {float(profile["pen"]["up_z_mm"]), float(profile["pen"]["down_z_mm"])}
        )
    unexpected_z = sorted({value for value in z_values if value not in allowed_z})
    last_motion = next(
        (line for line in reversed(text.splitlines()) if re.match(r"\s*G(?:0|1)\b", line)), ""
    )
    return {
        "path": str(path.relative_to(ROOT)),
        "forbidden_commands": forbidden,
        "extrusion_moves": extrusion,
        "nonfinite_tokens": nonfinite,
        "xy_out_of_workspace": xy_out,
        "unexpected_z_values": unexpected_z,
        "last_motion": last_motion,
        "safe": not (forbidden or extrusion or nonfinite or xy_out or unexpected_z),
    }


def font_analysis() -> dict:
    text = (REPORT / "analysis/docx-extracted.txt").read_text(encoding="utf-8")
    with TTFont(ROOT / "assets/1.ttf") as font:
        cmap = font.getBestCmap()
    chars = sorted({char for char in text if not char.isspace()}, key=ord)
    missing = [char for char in chars if ord(char) not in cmap]
    focus = ["ъ", "ь", "ы", "й", "ё", ".", ":", ";", "?"]
    return {
        "unique_non_whitespace_characters": len(chars),
        "missing": missing,
        "focus_coverage": {char: ord(char) in cmap for char in focus},
    }


def centerline_analysis(report: dict) -> dict:
    cache = load(ROOT / report["centerline"]["cache"])
    glyphs = cache["glyphs"]
    ranked = []
    for char, glyph in glyphs.items():
        quality = glyph.get("quality", {})
        score = (
            int(bool(quality.get("needs_review"))) * 100
            + max(0.0, 1.0 - float(quality.get("mask_coverage", 1.0))) * 10
            + float(quality.get("retrace_ratio", 0.0)) * 5
            + int(bool(quality.get("fallback_used"))) * 20
        )
        ranked.append((score, char, glyph))
    ranked.sort(key=lambda item: (-item[0], ord(item[1])))

    def compact(item: tuple) -> dict:
        _, char, glyph = item
        q = glyph.get("quality", {})
        return {
            "glyph": char,
            "warnings": glyph.get("warnings", []),
            "skeleton_method": q.get("skeleton_method"),
            "mask_coverage": q.get("mask_coverage"),
            "inside_mask_ratio": q.get("centerline_inside_mask_ratio"),
            "components": q.get("centerline_components"),
            "endpoints": q.get("endpoints"),
            "junctions": q.get("junctions", q.get("junction_count")),
            "odd_vertices": q.get("odd_vertices"),
            "strokes_before_routing": q.get("strokes_before_routing"),
            "strokes_after_routing": q.get("strokes_after_routing"),
            "pen_lifts_saved": q.get("pen_lifts_saved"),
            "retrace_ratio": q.get("retrace_ratio"),
            "fallback_used": q.get("fallback_used"),
        }

    focus = {}
    for char in ("ъ", "ь", "ы", "ж", "щ", "ф"):
        focus[char] = compact((0, char, glyphs[char])) if char in glyphs else {"metric": "not compiled"}
    return {"worst_10": [compact(item) for item in ranked[:10]], "routing_focus": focus}


def determinism() -> dict:
    first = REPORT / "jobs/docx-centerline-hybrid-a5"
    second = REPORT / "jobs/docx-centerline-hybrid-a5-repeat"
    patterns = ["output.gcode", "plotter-preview.svg", "pages/*/paths.json"]
    result = {}
    for pattern in patterns:
        left = sorted(first.glob(pattern))
        right = sorted(second.glob(pattern))
        left_hashes = [digest(path) for path in left]
        right_hashes = [digest(path) for path in right]
        result[pattern] = {
            "left_count": len(left),
            "right_count": len(right),
            "byte_identical": left_hashes == right_hashes,
            "left_sha256": left_hashes,
            "right_sha256": right_hashes,
        }
    r1, r2 = load(first / "report.json"), load(second / "report.json")
    changed = sorted(key for key in set(r1) | set(r2) if r1.get(key) != r2.get(key))
    result["report_changed_top_level_fields"] = changed
    normalized_equal = True
    for left_path, right_path in zip(
        sorted(first.glob("pages/*/paths.json")),
        sorted(second.glob("pages/*/paths.json")),
        strict=True,
    ):
        left_data, right_data = load(left_path), load(right_path)
        for data in (left_data, right_data):
            for stroke in data.get("strokes", []):
                stroke.pop("source_path", None)
        normalized_equal &= left_data == right_data
    result["paths_geometry_identical_ignoring_source_path"] = normalized_equal
    return result


def main() -> None:
    interrupted_benchmark = {
        "name": "benchmark-conversion",
        "rendered_command": ".venv/bin/python tools/benchmark_conversion.py plotter_pipeline_full_test.docx --font assets/1.ttf --runs 3 --output report/benchmark/conversion.json --page A5 --size normal --font-mode centerline --document-layout hybrid",
        "exit_code": 130,
        "status": "interrupted after approximately 12 minutes with run-000 incomplete",
    }
    command_log = REPORT / "commands.log"
    existing_commands = command_log.read_text(encoding="utf-8") if command_log.exists() else ""
    if '"name": "benchmark-conversion"' not in existing_commands:
        with command_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(interrupted_benchmark, ensure_ascii=False) + "\n")
    reports = {}
    for path in sorted((REPORT / "jobs").glob("*/report.json")):
        data = load(path)
        reports[path.parent.name] = {
            "status": data.get("status"),
            "error": data.get("error"),
            "warnings": data.get("warnings", []),
            "pages": data.get("statistics", {}).get("pages"),
            "statistics": data.get("statistics", {}),
            "motion": data.get("motion", {}),
            "cache": data.get("cache", {}),
            "centerline": data.get("centerline", {}),
            "handwriting": data.get("handwriting", {}),
            "latex": data.get("latex", {}),
            "document_import": data.get("document_import", {}),
            "document_layout": data.get("document_layout", {}),
            "semantic_objects": data.get("semantic_objects", {}),
            "pagination": data.get("pagination", {}),
            "performance": data.get("performance", {}),
        }
    primary = load(REPORT / "jobs/docx-centerline-hybrid-a5/report.json")
    machine = yaml.safe_load((ROOT / "configs/machine.yaml").read_text(encoding="utf-8"))
    gcode = [gcode_audit(path, machine) for path in sorted((REPORT / "jobs").rglob("*.gcode"))]
    regen_original = REPORT / "jobs/connections-safe/output.gcode"
    regen = REPORT / "analysis/connections-safe-regenerated.gcode"
    regeneration = {
        "original_sha256": digest(regen_original),
        "regenerated_sha256": digest(regen),
        "byte_identical": digest(regen_original) == digest(regen),
        "functional_body_identical": [
            line for line in regen_original.read_text(encoding="utf-8").splitlines()
            if not line.startswith(";")
        ] == [
            line for line in regen.read_text(encoding="utf-8").splitlines()
            if not line.startswith(";")
        ],
    }
    centerline = centerline_analysis(primary)
    (REPORT / "analysis/worst-glyphs.json").write_text(
        json.dumps(centerline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    payload = {
        "environment": {
            "branch": "master",
            "head": "708cd7ac734bd57088e4590700a56e1f39062a51",
            "python": "Python 3.12.3",
            "initial_worktree": "dirty: 3 untracked control/prompt files",
            "font": "assets/1.ttf",
            "inputs": ["plotter_pipeline_full_test.docx", "plotter_pipeline_full_test.pdf"],
        },
        "baseline": {"lint": "passed after audit-tool lint cleanup", "test": "239 passed", "smoke": "passed"},
        "jobs": reports,
        "font": font_analysis(),
        "centerline": centerline,
        "determinism": determinism(),
        "gcode_safety": {
            "files_checked": len(gcode),
            "all_safe": all(item["safe"] for item in gcode),
            "results": gcode,
            "regeneration": regeneration,
        },
        "benchmark": {
            "status": "incomplete",
            "reason": "cold run did not complete after approximately 12 minutes; stopped without canonical cache deletion",
            "partial_artifacts": [
                "report/benchmark/conversion-runs/run-000/extracted.txt",
                "report/benchmark/conversion-runs/run-000/document-structure.json",
            ],
        },
        "metric_gaps": [
            "centerline.worst_glyphs is empty despite 12 needs_review glyphs",
            "accepted/rejected connection pair geometry is not exported as JSON for multi-page jobs",
            "classification_conflicts and duplicate_primitives_suppressed are hard-coded zero",
            "report does not expose table merge/header/border-dedup metrics",
            "report does not expose image micro-stroke/spur/drift metrics",
        ],
        "finding_counts": {"P0": 1, "P1": 5, "P2": 5, "P3": 2, "total": 13},
        "findings": [
            {"id": "F-001", "priority": "P0", "category": "BUG", "title": "PDF math centerline route aborts both layouts"},
            {"id": "F-002", "priority": "P1", "category": "BUG", "title": "python -m entrypoint discards failure exit code"},
            {"id": "F-003", "priority": "P1", "category": "BUG", "title": "Three source VML arrows collapse to one"},
            {"id": "F-004", "priority": "P1", "category": "BUG/CONFIGURATION", "title": "Advertised A4 conflicts with default workspace"},
            {"id": "F-005", "priority": "P1", "category": "QUALITY LIMITATION", "title": "Twelve real glyphs need centerline review"},
            {"id": "F-006", "priority": "P1", "category": "PERFORMANCE BOTTLENECK", "title": "Warm primary conversion takes about 126.7 seconds"},
            {"id": "F-007", "priority": "P2", "category": "BUG", "title": "DOCX extract omits tables and OMML"},
            {"id": "F-008", "priority": "P2", "category": "MAINTAINABILITY/OBSERVABILITY", "title": "paths.json bytes depend on output directory"},
            {"id": "F-009", "priority": "P2", "category": "MAINTAINABILITY/OBSERVABILITY", "title": "Key report fields are empty or hard-coded"},
            {"id": "F-010", "priority": "P2", "category": "QUALITY LIMITATION", "title": "Aggressive connections do not change stress corpus geometry"},
            {"id": "F-011", "priority": "P2", "category": "QUALITY LIMITATION", "title": "Center/right DOCX tabs are approximated"},
            {"id": "F-012", "priority": "P3", "category": "MAINTAINABILITY", "title": "G-code subcommand omits full-run metadata comments"},
            {"id": "F-013", "priority": "P3", "category": "MAINTAINABILITY", "title": "Paginator concentrates too many policies"},
        ],
        "top_5": ["F-001", "F-002", "F-003", "F-005", "F-004"],
    }
    (REPORT / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = []
    for path in sorted(REPORT.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.json":
            continue
        relative = path.relative_to(ROOT)
        parts = relative.parts
        job = parts[2] if len(parts) > 2 and parts[1] == "jobs" else None
        if path.name == "report.json":
            artifact_type = "job-report"
        elif path.suffix == ".gcode":
            artifact_type = "gcode"
        elif path.suffix == ".svg":
            artifact_type = "svg-preview-debug"
        elif path.suffix == ".png":
            artifact_type = "raster-debug-source"
        elif path.suffix == ".json":
            artifact_type = "json-analysis-debug"
        elif path.suffix in {".log", ".txt"}:
            artifact_type = "log-or-text"
        elif path.suffix in {".md", ".html"}:
            artifact_type = "human-report-index"
        else:
            artifact_type = "other"
        manifest.append(
            {
                "relative_path": str(relative),
                "size": path.stat().st_size,
                "sha256": digest(path),
                "job": job,
                "artifact_type": artifact_type,
            }
        )
    (REPORT / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
