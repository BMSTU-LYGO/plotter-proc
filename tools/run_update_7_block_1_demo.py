from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and run the complete UPD 7 block 1 example suite."
    )
    parser.add_argument("--font", type=Path, default=Path("assets/1.ttf"))
    parser.add_argument(
        "--examples", type=Path, default=Path("examples/update_7/block_1")
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("build/update_7/block_1-example")
    )
    args = parser.parse_args()

    font = args.font.resolve()
    examples = args.examples.resolve()
    output_root = args.output_root.resolve()
    if not font.is_file():
        raise FileNotFoundError(f"Font not found: {font}")

    subprocess.run(
        [
            sys.executable,
            "tools/generate_update_7_fixtures.py",
            "--examples-output",
            str(examples),
        ],
        check=True,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")
    shared = [
        sys.executable,
        "-m",
        "plotter_processor",
        "run",
        "--font",
        str(font),
        "--font-mode",
        "centerline",
        "--centerline-cache",
        str(output_root / "shared-font-cache.json"),
        "--latex-stroke-mode",
        "centerline",
        "--strict-latex-quality",
        "--latex-debug",
        "--page",
        "A5",
    ]
    jobs = [
        (
            "semantic-omml",
            examples / "semantic-omml.docx",
            ["--latex", "mathtext", "--pdf-math", "off"],
        ),
        (
            "pdf-visual-math",
            examples / "pdf-visual-math.pdf",
            ["--latex", "auto", "--pdf-math", "visual", "--math-debug"],
        ),
    ]

    results: list[dict[str, object]] = []
    for name, source, extra in jobs:
        output = output_root / name
        command = [*shared, str(source), *extra, "--output-dir", str(output)]
        print(f"Running {name}...", flush=True)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (output / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        report = _read_json(output / "report.json")
        unsafe_tokens = _unsafe_gcode_tokens(output / "output.gcode")
        latex = report.get("latex", {})
        results.append(
            {
                "name": name,
                "input": str(source),
                "output": str(output),
                "returncode": completed.returncode,
                "status": report.get("status", "error"),
                "expressions_found": latex.get("expressions_found", 0),
                "semantic_expressions": latex.get("semantic_expressions", 0),
                "omml_expressions": latex.get("omml_expressions", 0),
                "pdf_visual_expressions": latex.get("pdf_visual_expressions", 0),
                "outline_fallbacks": latex.get("outline_fallbacks", 0),
                "needs_review": latex.get("needs_review", 0),
                "unsafe_gcode_tokens": unsafe_tokens,
                "artifacts": {
                    "preview": _existing(output / "plotter-preview.svg"),
                    "paths": _existing(output / "paths.json"),
                    "report": _existing(output / "report.json"),
                    "gcode": _existing(output / "output.gcode"),
                },
            }
        )

    success = all(
        result["returncode"] == 0
        and result["status"] == "ok"
        and not result["unsafe_gcode_tokens"]
        and result["outline_fallbacks"] == 0
        and result["needs_review"] == 0
        for result in results
    )
    coverage = {
        result["name"]: (
            result["semantic_expressions"],
            result["omml_expressions"],
            result["pdf_visual_expressions"],
        )
        for result in results
    }
    success = success and coverage == {
        "semantic-omml": (2, 1, 0),
        "pdf-visual-math": (0, 0, 2),
    }
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
        line = raw_line.split(";", 1)[0].strip().upper()
        if not line:
            continue
        tokens = line.split()
        command = tokens[0]
        if command in {"G28", "M104", "M109", "M140", "M190"}:
            findings.add(command)
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
