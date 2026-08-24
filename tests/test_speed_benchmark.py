import re
import subprocess
import sys
from pathlib import Path

from tools.benchmark_conversion import (
    _gcode_is_safe,
    _performance_summary,
    _verification_summary,
)


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
    assert "--warmup-runs" in result.stdout


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


def test_benchmark_verification_checks_speed_determinism_and_safety() -> None:
    baseline = {
        "warm_median_ms": 2000.0,
        "runs": [
            {
                "page_count": 1,
                "artifacts_sha256": {"paths": "geometry", "gcode": "safe"},
            }
        ],
    }
    current = {
        "warm_median_ms": 1000.0,
        "runs": [
            {
                "page_count": 1,
                "gcode_safety": "passed",
                "artifacts_sha256": {"paths": "geometry", "gcode": "safe"},
            },
            {
                "page_count": 1,
                "gcode_safety": "passed",
                "artifacts_sha256": {"paths": "geometry", "gcode": "safe"},
            },
        ],
    }

    summary = _verification_summary(baseline, current)

    assert summary == {
        "baseline_warm_median_ms": 2000.0,
        "current_warm_median_ms": 1000.0,
        "speedup": 2.0,
        "geometry_equal": True,
        "gcode_equal": True,
        "pages_equal": True,
        "deterministic_paths": True,
        "deterministic_gcode": True,
        "gcode_safety": True,
        "regression_free": True,
    }


def test_benchmark_gcode_safety_scans_generated_commands(tmp_path: Path) -> None:
    safe = tmp_path / "safe.gcode"
    unsafe = tmp_path / "unsafe.gcode"
    safe.write_text("G21\nG90\nG0 X1 Y2\nM84\n", encoding="utf-8")
    unsafe.write_text("G21\nG1 X1 E0.5\n", encoding="utf-8")

    assert _gcode_is_safe(safe)
    assert not _gcode_is_safe(unsafe)
