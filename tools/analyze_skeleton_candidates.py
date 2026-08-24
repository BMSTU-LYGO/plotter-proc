"""Summarize dual skeleton-candidate decisions from a sharded font cache."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def analyze(shard_directory: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for path in sorted(shard_directory.glob("U+*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for char, glyph in payload["glyphs"].items():
            quality = glyph["quality"]
            scores = dict(quality["candidate_scores"])
            winner = str(quality["skeleton_method"])
            values = sorted(float(score) for score in scores.values())
            rows.append(
                {
                    "glyph": char,
                    "codepoint": f"U+{ord(char):04X}",
                    "candidate_methods": list(scores),
                    "candidate_scores": scores,
                    "winner": winner,
                    "score_delta": round(values[1] - values[0], 6)
                    if len(values) == 2
                    else None,
                    "candidate_metrics": quality["candidate_metrics"],
                    "selected_quality": {
                        key: quality.get(key)
                        for key in (
                            "mask_coverage",
                            "reconstruction_extra",
                            "retrace_ratio",
                            "junctions",
                            "short_edges",
                            "micro_loops",
                            "needs_review",
                        )
                    },
                    "warnings": glyph.get("warnings", []),
                }
            )
    rows.sort(key=lambda row: ord(str(row["glyph"])))
    winners = Counter(str(row["winner"]) for row in rows)
    dual = [row for row in rows if len(row["candidate_methods"]) == 2]
    return {
        "glyph_count": len(rows),
        "dual_candidate_glyph_count": len(dual),
        "winner_counts": dict(sorted(winners.items())),
        "winner_percent": {
            method: round(count * 100.0 / max(1, len(rows)), 3)
            for method, count in sorted(winners.items())
        },
        "glyphs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("shard_directory", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("build/skeleton-candidate-audit.json")
    )
    args = parser.parse_args()
    result = analyze(args.shard_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "glyphs"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
