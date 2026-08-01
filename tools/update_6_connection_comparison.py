from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    reports = {
        mode: json.loads((args.root / mode / "report.json").read_text(encoding="utf-8"))
        for mode in ("off", "safe", "aggressive")
    }
    comparison = {
        "version": 1,
        "modes": {mode: report["handwriting"] for mode, report in reports.items()},
    }
    (args.root / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="180">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for index, mode in enumerate(("off", "safe", "aggressive")):
        metrics = reports[mode]["handwriting"]
        x = 30 + index * 290
        parts.append(f'<text x="{x}" y="40" font-size="22">{mode}</text>')
        parts.append(
            f'<text x="{x}" y="75" font-size="16">connected: '
            f'{metrics["connected_pairs"]}/{metrics["letter_pairs_total"]}</text>'
        )
        parts.append(
            f'<text x="{x}" y="105" font-size="16">lifts after: '
            f'{metrics["pen_lifts_inside_words_after"]}</text>'
        )
        parts.append(
            f'<text x="{x}" y="135" font-size="16">connector mm: '
            f'{metrics["connector_draw_length_mm"]}</text>'
        )
    parts.append("</svg>")
    (args.root / "contact-sheet.svg").write_text("\n".join(parts) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
