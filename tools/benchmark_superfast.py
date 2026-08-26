"""Deterministic normal-vs-SuperFast physical-route benchmark."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from plotter_processor.models import PlotterStroke, Point
from plotter_processor.path_optimizer import RetraceConfig, optimize_word_strokes
from plotter_processor.routing_cost import RoutingCostWeights

SCENARIOS = {
    "short": "Привет, как дела?",
    "complex_cyrillic": "ж м т ш щ ы ь ъ",
    "multiline": (
        "Мама мыла раму, а потом писала письмо.\n"
        "Хороший плоттер пишет слова быстро и аккуратно!"
    ),
}

_PUNCTUATION = frozenset(".,:;!?")
_COMPLEX = frozenset("жмтшщыьъ")


@dataclass(frozen=True, slots=True)
class _WordGeometry:
    text: str
    strokes: list[PlotterStroke]
    punctuation: bool = False


def run_benchmark() -> dict[str, object]:
    scenarios = {
        name: _compare_scenario(text) for name, text in SCENARIOS.items()
    }
    return {
        "benchmark": "UPD_Plotter_19_SuperFast",
        "scenarios": scenarios,
        "summary": _summary(scenarios),
    }


def _compare_scenario(text: str) -> dict[str, object]:
    words = _scenario_geometry(text)
    normal_config = RetraceConfig(enabled=True, max_length_mm=1.2, max_repeats=1)
    superfast_config = RetraceConfig(
        enabled=True,
        max_length_mm=3.0,
        max_repeats=3,
        allowed_segment_types=frozenset({"glyph", "connector", "snap", "retrace"}),
        mode="superfast",
        endpoint_tolerance_mm=0.08,
        max_retrace_ratio=0.65,
        weights=RoutingCostWeights(pen_lift=24.0, retrace=0.65),
    )
    normal = _route_scenario(words, normal_config)
    superfast = _route_scenario(words, superfast_config)
    return {
        "text": text,
        "normal": normal,
        "superfast": superfast,
        "improvement": {
            "pen_up_reduction": normal["pen_up"] - superfast["pen_up"],
            "travel_reduction_mm": round(
                normal["travel_path_mm"] - superfast["travel_path_mm"], 6
            ),
            "estimated_time_reduction_seconds": round(
                normal["estimated_time_seconds"]
                - superfast["estimated_time_seconds"],
                6,
            ),
        },
    }


def _route_scenario(
    words: list[_WordGeometry], config: RetraceConfig
) -> dict[str, object]:
    routed: list[PlotterStroke] = []
    passes: list[int] = []
    retrace = 0.0
    fallbacks = 0
    for word in words:
        if word.punctuation:
            optimized = word.strokes
            report: dict[str, object] = {
                "continuous_passes": len(optimized),
                "retrace_distance_mm": 0.0,
                "fallback_used": False,
            }
        else:
            optimized, report = optimize_word_strokes(word.strokes, config)
            passes.append(int(report["continuous_passes"]))
        retrace += float(report["retrace_distance_mm"])
        fallbacks += int(bool(report.get("fallback_used", False)))
        routed.extend(optimized)
    drawing = sum(_polyline_length(stroke.points) for stroke in routed)
    travel = sum(
        _distance(left.points[-1], right.points[0])
        for left, right in pairwise(routed)
    )
    pen_actions = len(routed)
    estimated = drawing / 25.0 + travel / 50.0 + pen_actions * 0.35
    return {
        "pen_up": pen_actions,
        "pen_down": pen_actions,
        "drawing_path_mm": round(drawing, 6),
        "travel_path_mm": round(travel, 6),
        "retrace_path_mm": round(retrace, 6),
        "estimated_time_seconds": round(estimated, 6),
        "word_passes": {
            "1": sum(value == 1 for value in passes),
            "2": sum(value == 2 for value in passes),
            ">2": sum(value > 2 for value in passes),
        },
        "fallback_words": fallbacks,
    }


def _scenario_geometry(text: str) -> list[_WordGeometry]:
    result: list[_WordGeometry] = []
    word_index = 0
    cursor_x = 0.0
    for line in text.splitlines():
        token = ""
        for char in f"{line} ":
            if char.isspace() or char in _PUNCTUATION:
                if token:
                    result.append(_word_geometry(token, word_index, cursor_x))
                    cursor_x += len(token) * 1.8 + 1.8
                    word_index += 1
                    token = ""
                if char in _PUNCTUATION:
                    result.append(_punctuation_geometry(char, word_index, cursor_x))
                    cursor_x += 1.2
                    word_index += 1
            else:
                token += char
        cursor_x = 0.0
    return result


def _word_geometry(text: str, word_index: int, x: float) -> _WordGeometry:
    end = x + max(1.8, len(text) * 1.8)
    complex_count = min(2, sum(char.lower() in _COMPLEX for char in text))
    junctions = [end - 1.4 + index * 0.15 for index in range(complex_count)]
    points = [Point(x, 0.0), *(Point(value, 0.0) for value in junctions), Point(end, 0.0)]
    main = PlotterStroke(
        id=word_index * 10,
        points=points,
        closed=False,
        glyph_index=word_index * 10,
        char=text,
        source_glyph_indices=tuple(range(word_index * 10, word_index * 10 + len(text))),
        source_chars=text,
        segment_types=("glyph", "connector", "glyph"),
        word_index=word_index,
    )
    strokes = [main]
    for branch_index in range(complex_count):
        junction_x = end - 1.4 + branch_index * 0.15
        strokes.append(
            PlotterStroke(
                id=word_index * 10 + branch_index + 1,
                points=[Point(junction_x, 0.0), Point(junction_x, -0.6)],
                closed=False,
                glyph_index=word_index * 10 + branch_index + 1,
                char=text[-1],
                source_glyph_indices=(word_index * 10 + branch_index + 1,),
                source_chars=text[-1],
                segment_types=("glyph",),
                word_index=word_index,
            )
        )
    return _WordGeometry(text, strokes)


def _punctuation_geometry(
    char: str, word_index: int, x: float
) -> _WordGeometry:
    stroke = PlotterStroke(
        id=word_index * 10,
        points=[Point(x + 0.25, 0.0), Point(x + 0.25, 0.2)],
        closed=False,
        glyph_index=word_index * 10,
        char=char,
        source_glyph_indices=(word_index * 10,),
        source_chars=char,
        segment_types=("glyph",),
        word_index=word_index,
    )
    return _WordGeometry(char, [stroke], True)


def _summary(scenarios: dict[str, dict[str, object]]) -> dict[str, object]:
    improvements = [item["improvement"] for item in scenarios.values()]
    return {
        "scenarios": len(scenarios),
        "total_pen_up_reduction": sum(
            int(item["pen_up_reduction"]) for item in improvements
        ),
        "total_estimated_time_reduction_seconds": round(
            sum(float(item["estimated_time_reduction_seconds"]) for item in improvements),
            6,
        ),
    }


def _polyline_length(points: list[Point]) -> float:
    return sum(_distance(left, right) for left, right in pairwise(points))


def _distance(left: Point, right: Point) -> float:
    return math.hypot(right.x - left.x, right.y - left.y)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("build/superfast-benchmark.json")
    )
    args = parser.parse_args()
    result = run_benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
