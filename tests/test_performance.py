import numpy as np

from plotter_processor.image_preprocessor import PreprocessedImage
from plotter_processor.image_vectorizer import vectorize_image
from plotter_processor.latex_renderer import MathTextRenderer
from plotter_processor.performance import StageTimings


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
