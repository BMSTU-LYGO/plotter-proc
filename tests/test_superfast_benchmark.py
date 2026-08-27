from tools.benchmark_superfast import SCENARIOS, run_benchmark


def test_superfast_benchmark_covers_required_scenarios_and_metrics() -> None:
    result = run_benchmark()

    assert SCENARIOS["short"] == "Привет, как дела?"
    assert all(char in SCENARIOS["complex_cyrillic"] for char in "жмтшщыьъ")
    assert "\n" in SCENARIOS["multiline"]
    assert len(result["scenarios"]) == 3
    for scenario in result["scenarios"].values():
        normal = scenario["normal"]
        superfast = scenario["superfast"]
        assert {
            "pen_up", "pen_down", "drawing_path_mm", "travel_path_mm",
            "retrace_path_mm", "estimated_time_seconds", "word_passes",
        } <= normal.keys()
        assert superfast["pen_up"] <= normal["pen_up"]
        assert superfast["estimated_time_seconds"] <= normal["estimated_time_seconds"]
        assert superfast["word_passes"][">2"] == 0
