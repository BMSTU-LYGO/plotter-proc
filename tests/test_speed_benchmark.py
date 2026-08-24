import re
import subprocess
import sys
from pathlib import Path

from tools.benchmark_conversion import _performance_summary


def test_speed_benchmark_contains_exactly_fifty_words() -> None:
    text = Path("examples/benchmark_50_words.txt").read_text(encoding="utf-8")
    assert len(re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", text)) == 50


def test_conversion_benchmark_exposes_separate_cold_and_warm_modes() -> None:
    result = subprocess.run(
        [sys.executable, "tools/benchmark_conversion.py", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "--cold-only" in result.stdout
    assert "--warm-only" in result.stdout
    assert "--warm-runs" in result.stdout


def test_conversion_benchmark_summarizes_stages_and_hotspots() -> None:
    results = [
        {
            "kind": "warm",
            "performance": {
                "total_ms": 12.0,
                "layout_ms": 3.0,
                "pages": [
                    {
                        "hotspots": {
                            "build_paths.transform": {"total_ms": 2.0},
                        }
                    }
                ],
            },
        },
        {
            "kind": "warm",
            "performance": {
                "total_ms": 10.0,
                "layout_ms": 1.0,
                "pages": [
                    {
                        "hotspots": {
                            "build_paths.transform": {"total_ms": 4.0},
                        }
                    }
                ],
            },
        },
    ]

    summary = _performance_summary(results)

    assert summary["warm_median_ms"]["stage.total_ms"] == 11.0
    assert summary["warm_median_ms"]["stage.layout_ms"] == 2.0
    assert summary["warm_median_ms"]["hotspot.build_paths.transform"] == 3.0
