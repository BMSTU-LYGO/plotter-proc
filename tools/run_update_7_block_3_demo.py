from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, default=Path("assets/1.ttf"))
    parser.add_argument("--output-root", type=Path, default=Path("build/update_7/candidate/block_3"))
    args = parser.parse_args()
    root = args.output_root.resolve()
    examples = Path("examples/update_7/block_3").resolve()
    subprocess.run([sys.executable, "tools/generate_update_7_fixtures.py", "--block-3-examples-output", str(examples)], check=True)
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ); env.setdefault("MPLCONFIGDIR", "/tmp/plotter-matplotlib-cache")
    expected = {
        "underlines": ("underlines.docx", "underlines", 4),
        "arrows": ("arrows.pdf", "arrows", 2),
        "simple-table": ("simple-table.docx", "tables", 1),
        "merged-table": ("merged-table.docx", "tables", 1),
        "multipage-table": ("multipage-table.docx", "table_pages", 2),
        "pdf-table": ("pdf-table.pdf", "tables", 1),
    }
    results = []
    for name, (filename, metric, minimum) in expected.items():
        output = root / name
        command = [sys.executable, "-m", "plotter_processor", "run", str(examples / filename), "--font", str(args.font.resolve()), "--font-mode", "centerline", "--centerline-cache", str(root / "shared-font-cache.json"), "--pdf-math", "off", "--semantic-debug", "--page", "A5", "--output-dir", str(output)]
        print(f"Running {name}...", flush=True)
        completed = subprocess.run(command, capture_output=True, text=True, env=env, check=False)
        output.mkdir(parents=True, exist_ok=True)
        (output / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
        (output / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
        report = _json(output / "report.json")
        semantic = report.get("semantic_objects", {})
        value = semantic.get(metric, 0) if isinstance(semantic, dict) else 0
        results.append({"name": name, "status": report.get("status", "error"), "returncode": completed.returncode, "metric": metric, "value": value, "minimum": minimum, "safe": _safe(output / "output.gcode"), "preview": str(output / "plotter-preview.svg"), "debug": str(output / "semantic-debug" / "classification.svg")})
    success = all(item["status"] == "ok" and item["returncode"] == 0 and item["safe"] and item["value"] >= item["minimum"] for item in results)
    summary = {"status": "ok" if success else "failed", "jobs": results}
    (root / "demo-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Demo {summary['status']}: {root / 'demo-summary.json'}")
    return 0 if success else 1


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text()) if path.is_file() else {}


def _safe(path: Path) -> bool:
    if not path.is_file(): return False
    text = path.read_text().upper()
    return all(token not in text for token in ("M104", "M109", "M140", "M190", "G28", "NAN", "INFINITY"))


if __name__ == "__main__":
    raise SystemExit(main())
