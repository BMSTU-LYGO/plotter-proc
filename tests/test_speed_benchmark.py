import re
from pathlib import Path


def test_speed_benchmark_contains_exactly_fifty_words() -> None:
    text = Path("examples/benchmark_50_words.txt").read_text(encoding="utf-8")
    assert len(re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", text)) == 50
