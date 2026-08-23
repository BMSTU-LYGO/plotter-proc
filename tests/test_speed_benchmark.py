import re
import subprocess
import sys
from pathlib import Path


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
