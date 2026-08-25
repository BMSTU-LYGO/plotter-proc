import numpy as np

from plotter_processor.image_preprocessor import PreprocessedImage
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.latex_renderer import MathTextRenderer
from plotter_processor.performance import (
    GLYPH_TIMING_STAGES,
    FunctionProfiler,
    HotspotTimings,
    PagePerformance,
    StageTimings,
    collect_glyph_performance,
    glyph_performance,
    measure_glyph_stage,
)


def test_stage_timings_reports_calls_total_and_max() -> None:
    timings = StageTimings()
    with timings.measure("layout"):
        sum(range(10))
    with timings.measure("layout"):
        sum(range(20))

    report = timings.report()
    assert report["layout_ms"] >= 0
    assert report["stages"]["layout"]["calls"] == 2
    assert report["stages"]["layout"]["max_ms"] >= 0
    assert report["total_ms"] >= report["layout_ms"]


def test_stage_timings_emits_optional_progress_events() -> None:
    events: list[tuple[str, str, float | None]] = []
    timings = StageTimings(lambda stage, state, elapsed: events.append((stage, state, elapsed)))

    with timings.measure("handwriting"):
        sum(range(10))

    assert events[0] == ("handwriting", "started", None)
    assert events[1][0:2] == ("handwriting", "completed")
    assert events[1][2] is not None and events[1][2] >= 0


def test_stage_timings_merges_worker_measurements() -> None:
    timings = StageTimings()

    timings.record("handwriting", 12.5)
    timings.record("handwriting", 7.5)

    report = timings.report()
    assert report["handwriting_ms"] == 20.0
    assert report["stages"]["handwriting"]["calls"] == 2
    assert report["stages"]["handwriting"]["max_ms"] == 12.5


def test_function_profiler_reports_top_functions_for_selected_stage() -> None:
    profiler = FunctionProfiler("handwriting")
    profiler.progress("handwriting", "started", None)
    sum(range(100))
    profiler.progress("handwriting", "completed", 0.1)

    rows = profiler.top_functions(20)
    assert rows
    assert all(
        {
            "function",
            "calls",
            "self_seconds",
            "cumulative_seconds",
            "seconds_per_call",
        }
        <= row.keys()
        for row in rows
    )


def test_page_performance_reports_required_fields() -> None:
    performance = PagePerformance(page=2, glyph_count=17)
    performance.values["stroke_count_before"] = 4
    performance.values["point_count_before"] = 23
    with performance.measure("word_routing_ms"):
        sum(range(10))

    report = performance.report()
    assert report["page"] == 2
    assert report["glyph_count"] == 17
    assert report["stroke_count_before"] == 4
    assert report["point_count_before"] == 23
    assert set(PagePerformance.TIMINGS) <= report.keys()


def test_hotspot_timings_are_opt_in_and_report_calls() -> None:
    disabled = PagePerformance(page=1, glyph_count=2)
    with disabled.hotspots.measure("build_paths.glyph_draw"):
        sum(range(10))
    assert "hotspots" not in disabled.report()

    enabled = PagePerformance(page=1, glyph_count=2, collect_hotspots=True)
    with enabled.hotspots.measure("build_paths.glyph_draw"):
        sum(range(10))
    enabled.hotspots.record("simplification.rdp", 1.25)

    report = enabled.report()
    assert report["hotspots"]["build_paths.glyph_draw"]["calls"] == 1
    assert report["hotspots"]["simplification.rdp"]["total_ms"] == 1.25
    assert isinstance(enabled.hotspots, HotspotTimings)


def test_glyph_performance_reports_every_compiler_stage() -> None:
    with collect_glyph_performance() as performance, glyph_performance("A"):
        for stage in GLYPH_TIMING_STAGES:
            with measure_glyph_stage(stage):
                sum(range(5))

    [report] = performance.report()
    assert report["glyph"] == "A"
    assert report["codepoint"] == "U+0041"
    assert report["total_ms"] >= 0
    assert all(f"{stage}_ms" in report for stage in GLYPH_TIMING_STAGES)


def test_latex_renderer_reuses_identical_local_geometry() -> None:
    renderer = MathTextRenderer(stroke_mode="outline")
    expression = r"x_{cache_test}^{17}"

    first = renderer.render(expression, 5.123)
    second = renderer.render(expression, 5.123)

    assert first is second
    assert renderer.cache_misses == 1
    assert renderer.cache_hits == 1


def test_image_vectorizer_reuses_pixel_geometry() -> None:
    grayscale = np.ones((20, 30), dtype=np.float32)
    grayscale[5:15, 14:16] = 0
    image = PreprocessedImage(
        grayscale,
        grayscale < 0.5,
        (30, 20),
        (30, 20),
        (),
    )
    options = {
        "edge": {"sigma": 1.0, "low_threshold": 0.08, "high_threshold": 0.2},
        "vector": {
            "simplify_tolerance_mm": 0.08,
            "min_stroke_length_mm": 0.1,
            "max_points_per_image": 1000,
            "max_strokes_per_image": 1000,
        },
    }

    vectorize_image(image, options, mode="centerline", width_mm=30, height_mm=20)
    second = vectorize_image(
        image, options, mode="centerline", width_mm=15, height_mm=10
    )

    assert second.cache_hit is True
